#!/usr/bin/env python3

import calendar
from contextlib import closing
import logging
import re
import signal
import socket
import socketserver
import functools
import threading
import time

HOST, PORT = '0.0.0.0', 8125

CARBON_IP = '127.0.0.1'
CARBON_PORT = 2003

METRIC_TYPE_COUNTER_SYMBOL = 'c'
METRIC_TYPE_TIMER_SYMBOL = 'ms'
METRIC_TYPE_GAUGE_SYMBOL = 'g'
DEFAULT_SAMPLE_RATE = 1.0

TIMER_MSG_FORMAT = '''%(key)s.lower %(min)s %(ts)s
%(key)s.count %(count)s %(ts)s
%(key)s.mean %(mean)s %(ts)s
%(key)s.upper %(max)s %(ts)s
%(key)s.upper_%(pct_threshold)s %(max_threshold)s %(ts)s
'''

COUNTER_MSG_FORMAT = '''%(key)s.count %(count)s %(ts)s
'''

GAUGE_MSG_FORMAT = '''%(key)s.gauge %(value)s %(ts)s
'''

FORMATS = {
    METRIC_TYPE_COUNTER_SYMBOL: COUNTER_MSG_FORMAT,
    METRIC_TYPE_TIMER_SYMBOL: TIMER_MSG_FORMAT,
    METRIC_TYPE_GAUGE_SYMBOL: GAUGE_MSG_FORMAT,
}

metrics = {
    METRIC_TYPE_COUNTER_SYMBOL: {},
    METRIC_TYPE_TIMER_SYMBOL: {},
    METRIC_TYPE_GAUGE_SYMBOL: {},
}

timer = None
server = None
lock = threading.Lock()

def process_lines(metric_lines):
    for line in metric_lines:
        line = line.strip('\0')
        if len(line) == 0:
            continue
        try:
            parsed_line = parse_line(line)
            add_metric(*parsed_line)
        except ValueError as e:
            logging.exception(e)


def parse_line(metric_line):
    '''
    Parse a line, extracting the key, data, metric type and sample rate.
    '''
    try:
        metric_line = metric_line.strip()
        components = metric_line.split(':')
        key = components[0]
        key = clean_key(key)
        components = components[1].split('|')
        data = float(components[0])
        metric_type = components[1]
        if metric_type not in metrics:
            raise LookupError("Invalid metric type '%s'" % metric_type)
        sample_rate = DEFAULT_SAMPLE_RATE
        if len(components) > 2:
            if metric_type != METRIC_TYPE_COUNTER_SYMBOL:
                raise ValueError(
                    "Sample rate illegal for non-counter type '%s'" % metric_type)
            sample_rate = float(components[2].split('@')[1])
        return key, data, metric_type, sample_rate
    except Exception as e:
        raise ValueError(f"{e} line: [{metric_line}]")


def add_metric(key, data, metric_type, sample_rate):
    with lock:
        metric_keys = metrics[metric_type]
        interval_data = metric_keys.setdefault(key, [])
        interval_data.append(data * (1 / sample_rate))

class memoized(object):
   '''Decorator. Caches a function's return value each time it is called.
   If called later with the same arguments, the cached value is returned 
   (not reevaluated).
   '''
   def __init__(self, func):
      self.func = func
      self.cache = {}
   def __call__(self, *args):
      try:
         return self.cache[args]
      except KeyError:
         value = self.func(*args)
         self.cache[args] = value
         return value
      except TypeError:
        # uncacheable -- for instance, passing a list as an argument.
         # Better to not cache than to blow up entirely.
         return self.func(*args)
   def __repr__(self):
      '''Return the function's docstring.'''
      return self.func.__doc__
   def __get__(self, obj, objtype):
      '''Support instance methods.'''
      return functools.partial(self.__call__, obj)

@memoized
def clean_key(key):
    '''
    Replace whitespace with '_', '/' with '-', and remove all
    non-alphanumerics remaining (except '.', '_', and '-').
    The cleaned key is returned in lowercase.
    '''
    new_key = re.sub(r'\s+', '_', key)
    new_key = new_key.replace('/', '-')
    new_key = re.sub(r'[^a-zA-Z_\-0-9\.]', '', new_key)
    return new_key.lower()


def calculate_interval_metrics():
    with lock:
        interval_metrics = []
        timestamp = calendar.timegm(time.gmtime())
        threshold = 90.0

        counters = metrics[METRIC_TYPE_COUNTER_SYMBOL]
        for key, values in counters.items():
            count = sum(values)
            metric = {
                'key' : key,
                'ts': timestamp,
                'count': count,
                'type': METRIC_TYPE_COUNTER_SYMBOL
            }
            interval_metrics.append(metric)

        timers = metrics[METRIC_TYPE_TIMER_SYMBOL]
        for key, values in timers.items():
            count = len(values)
            values.sort()
            min_val = values[0]
            max_val = values[-1]

            mean = min_val
            max_threshold = max_val
            if count > 1:
                thresh_index = int((threshold / 100.0) * count)
                max_threshold = values[thresh_index - 1]
                total = sum(values)
                mean = total / count

            metric = {
                'key': key,
                'ts': timestamp,
                'min': min_val,
                'max': max_val,
                'mean': mean,
                'count': count,
                'max_threshold': max_threshold,
                'pct_threshold': int(threshold),
                'type': METRIC_TYPE_TIMER_SYMBOL
            }
            interval_metrics.append(metric)

        gauges = metrics[METRIC_TYPE_GAUGE_SYMBOL]
        for key, values in gauges.items():
            last = values[-1]
            metric = {
                'key' : key,
                'ts': timestamp,
                'value': last,
                'type': METRIC_TYPE_GAUGE_SYMBOL
            }
            interval_metrics.append(metric)

        return interval_metrics


def format_metrics(interval_metrics):
    # create the strings
    # send them to the carbon server
    message_lines = []
    for metric in interval_metrics:
        lines = format_metric(metric)
        message_lines.append(lines)
    return message_lines


def format_metric(metric):
    metric_type = metric['type']
    format_str = FORMATS[metric_type]
    return format_str % metric


def send_metrics(formatted_metrics):
    # FIXME Keep a connection to carbon open all the time
    message = ''.join(formatted_metrics)
    with closing(socket.create_connection((CARBON_IP, CARBON_PORT))) as carbon:
        carbon.sendall(message)


def flush_metrics():
    try:
        interval_metrics = calculate_interval_metrics()
        # add internal metrics
        if len(interval_metrics) > 0:
            formatted_metrics = format_metrics(interval_metrics)
            send_metrics(formatted_metrics)
    finally:
        try:
            clear_metrics()
        finally:
            schedule_flush()


def clear_metrics():
    with lock:
        for metric_type, metric_keys in metrics.items():
            metric_keys.clear()


def schedule_flush():
    global timer
    timer = threading.Timer(1, flush_metrics)
    timer.start()


class StatsDHandler(socketserver.DatagramRequestHandler):
    '''
    Request handler for the StatsD 'protocol'
    '''
    def handle(self):
        metric_lines = self.rfile.readlines()
        process_lines(metric_lines)


def serve():
    global server
    server = socketserver.UDPServer((HOST, PORT), StatsDHandler)
    server.serve_forever()


def signal_handler(signal, frame):
    global timer
    global server
    if timer:
        timer.cancel()
    if server:
        server.shutdown()


def serve_forever():
    thread = threading.Thread(target=serve)
    thread.daemon = True
    thread.start()

    while thread.is_alive():
        thread.join(0.2)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    schedule_flush()
    serve_forever()


if __name__ == '__main__':
    main()

# If you want to use the server as a module, move this file's logic into py_statsd_min/__init__.py or another module file.
# For now, just import from this file if needed.
