#!/usr/bin/env python

import calendar
from contextlib import closing
import signal
import socket
import SocketServer
import threading
import time

HOST, PORT = 'localhost', 9999

CARBON_IP = '127.0.0.1'
CARBON_PORT = 9998

METRIC_TYPE_COUNTER_SYMBOL = 'c'
METRIC_TYPE_TIMER_SYMBOL = 'ms'
METRIC_TYPE_GAUGE_SYMBOL = 'g'
DEFAULT_SAMPLE_RATE = 1

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

def process_lines(metric_lines):
    for line in metric_lines:
        # FIXME Need to catch exceptions thrown from parse_line so we don't
        # throw away other good metrics due to a single bad input line
        parsed_line = parse_line(line)
        # FIXME same here, don't want to break out of this loop due to a
        # single bad metric
        add_metric(*parsed_line)


def parse_line(metric_line):
    '''
    Parse a line, extracting the key, data, metric type and sample rate.
    '''
    metric_line = metric_line.strip()
    components = metric_line.split(':')
    key = components[0]
    key = clean_key(key)
    components = components[1].split('|')
    data = float(components[0])
    metric_type = components[1]
    sample_rate = DEFAULT_SAMPLE_RATE
    if len(components) > 2:
        if metric_type != METRIC_TYPE_COUNTER_SYMBOL:
            raise RuntimeError
        sample_rate = float(components[2].split('@')[1])
    return key, data, metric_type, sample_rate


def add_metric(key, data, metric_type, sample_rate):
    metric_keys = metrics[metric_type]
    interval_data = metric_keys.setdefault(key, [])
    interval_data.append(data * (1 / sample_rate))


def clean_key(key):
    '''
    Replace whitespace with '_', '/' with '-', and remove all
    non-alphanumerics remaining (except '.').
    '''
    return key


def calculate_interval_metrics():
    interval_metrics = []
    timestamp = calendar.timegm(time.gmtime())
    threshold = 90.0

    counters = metrics[METRIC_TYPE_COUNTER_SYMBOL]
    for key, values in counters.iteritems():
        count = sum(values)
        metric = {
            'key' : key,
            'ts': timestamp,
            'count': count,
            'type': METRIC_TYPE_COUNTER_SYMBOL
        }
        interval_metrics.append(metric)

    timers = metrics[METRIC_TYPE_TIMER_SYMBOL]
    for key, values in timers.iteritems():
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
            'pct_threshold': threshold,
            'type': METRIC_TYPE_TIMER_SYMBOL
        }
        interval_metrics.append(metric)

    gauges = metrics[METRIC_TYPE_GAUGE_SYMBOL]
    for key, values in gauges.iteritems():
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
    interval_metrics = calculate_interval_metrics()
    # add internal metrics
    if len(interval_metrics) > 0:
        formatted_metrics = format_metrics(interval_metrics)
        send_metrics(formatted_metrics)
    clear_metrics()
    schedule_flush()


def clear_metrics():
    for metric_type, metric_keys in metrics.iteritems():
        metric_keys.clear()


def schedule_flush():
    global timer
    timer = threading.Timer(1, flush_metrics)
    timer.start()


def serve():
    print 'Listening on %s:%d' % (HOST, PORT)
    global server
    server = SocketServer.UDPServer((HOST, PORT), StatsDHandler)
    server.serve_forever()


def signal_handler(signal, frame):
    global timer
    global server
    timer.cancel()
    server.shutdown()


class StatsDHandler(SocketServer.DatagramRequestHandler):
    '''
    Request handler for the StatsD 'protocol'
    '''
    def handle(self):
        metric_lines = self.rfile.readlines()
        process_lines(metric_lines)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    schedule_flush()

    thread = threading.Thread(target=serve)
    thread.daemon = True
    thread.start()

    # Apparently `thread.join` blocks the main thread and makes it
    # _uninterruptable_, so we need to do this loop so that the main
    # thread can respond to signal handlers.
    while thread.isAlive():
        thread.join(0.2)


if __name__ == '__main__':
    main()



# a thread needs to be running that will wake up on a timer and send the collected data somewhere else