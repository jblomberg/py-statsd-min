import py_statsd_min.server as server

import unittest

class ServerTestSuite(unittest.TestCase):
    '''StatsD server test cases'''
    def setUp(self):
        server.clear_metrics()
    def test_clean_key(self):
        key = server.clean_key('test key')
        self.assertEqual(key, 'test_key')

        key = server.clean_key('test/key')
        self.assertEqual(key, 'test-key')

        key = server.clean_key('test!key')
        self.assertEqual(key, 'testkey')

        key = server.clean_key('test.key')
        self.assertEqual(key, 'test.key')

        key = server.clean_key('TESTKEY')
        self.assertEqual(key, 'testkey')

    def test_parse_line_invalid(self):
        self.assertRaises(ValueError, server.parse_line, 'keyonly')
        self.assertRaises(ValueError, server.parse_line, 'noval:')
        self.assertRaises(ValueError, server.parse_line, 'nocolon 1|c')
        self.assertRaises(ValueError, server.parse_line, 'notype:1')
        self.assertRaises(ValueError, server.parse_line, 'notype:1|')
        self.assertRaises(ValueError, server.parse_line, 'nosep:1 c')
        self.assertRaises(ValueError, server.parse_line, 'badtype:1|a')
        self.assertRaises(ValueError, server.parse_line, 'badval:help|c')

    def test_parse_line_counter(self):
        metric = server.parse_line('test.key: 1|c')
        self.assertEqual(metric, ('test.key', 1.0, 'c', 1.0))

        metric = server.parse_line('test.key: 1|c|@0.1')
        self.assertEqual(metric, ('test.key', 1.0, 'c', 0.1))

        line = 'test.key: 1|c|2'
        self.assertRaises(ValueError, server.parse_line, line)

    def test_parse_line_gauge(self):
        metric = server.parse_line('test.key: 5|g')
        self.assertEqual(metric, ('test.key', 5.0, 'g', 1.0))

        self.assertRaises(ValueError, server.parse_line, 'test:5|g|@0.1')

    def test_parse_line_duration(self):
        metric = server.parse_line('test.key: 34.5|ms')
        self.assertEqual(metric, ('test.key', 34.5, 'ms', 1.0))

        self.assertRaises(ValueError, server.parse_line, 'test:5|ms|@0.1')

    def test_add_metric(self):
        server.add_metric('test.key', 1.0, 'c', 1.0)
        self.assertEqual(server.metrics['c']['test.key'], [1.0])

        server.add_metric('test.key', 1.0, 'c', 0.1)
        self.assertEqual(server.metrics['c']['test.key'], [1.0, 10.0])

        server.add_metric('test.key', 1.0, 'ms', 1.0)
        self.assertEqual(server.metrics['ms']['test.key'], [1.0])
        server.add_metric('test.key', 1.0, 'ms', 1.0)
        self.assertEqual(server.metrics['ms']['test.key'], [1.0, 1.0])

        server.add_metric('gauge.key', 2.0, 'g', 1.0)
        self.assertEqual(server.metrics['g']['gauge.key'], [2.0])
        server.add_metric('gauge.key', 4.0, 'g', 1.0)
        self.assertEqual(server.metrics['g']['gauge.key'], [2.0, 4.0])

    def test_process_lines(self):
        lines = [
            'test.key: 1|c\n',
            'badline',
            'test.key: 2|c\n',
            'test.key2: 20|ms\n',
            'test.gauge: 10|g\n',
            ]
        server.process_lines(lines)
        self.assertEqual(server.metrics['c']['test.key'], [1.0, 2.0])
        self.assertEqual(server.metrics['ms']['test.key2'], [20.0])
        self.assertEqual(server.metrics['g']['test.gauge'], [10.0])

    def test_clear_metrics(self):
        server.add_metric('foo', 1, 'c', 1.0)
        server.add_metric('bar', 2, 'ms', 1.0)
        server.add_metric('baz', 3, 'g', 1.0)
        server.clear_metrics()
        self.assertEqual(server.metrics['c'], {})
        self.assertEqual(server.metrics['ms'], {})
        self.assertEqual(server.metrics['g'], {})

    def test_calculate_and_format_metrics(self):
        server.add_metric('counter.key', 5, 'c', 1.0)
        server.add_metric('counter.key', 3, 'c', 1.0)
        server.add_metric('timer.key', 10, 'ms', 1.0)
        server.add_metric('timer.key', 30, 'ms', 1.0)
        server.add_metric('gauge.key', 3, 'g', 1.0)
        server.add_metric('gauge.key', 5, 'g', 1.0)

        metrics_list = server.calculate_interval_metrics()
        metrics_dict = {(m['key'], m['type']): m for m in metrics_list}

        counter = metrics_dict[('counter.key', 'c')]
        self.assertEqual(counter['count'], 8)

        timer = metrics_dict[('timer.key', 'ms')]
        self.assertEqual(timer['min'], 10)
        self.assertEqual(timer['max'], 30)
        self.assertEqual(timer['mean'], 20)
        self.assertEqual(timer['count'], 2)
        self.assertEqual(timer['max_threshold'], 10)
        self.assertEqual(timer['pct_threshold'], 90)

        gauge = metrics_dict[('gauge.key', 'g')]
        self.assertEqual(gauge['value'], 5)

        msg_counter = server.format_metric(counter)
        self.assertIn('counter.key.count 8', msg_counter)

        msg_timer = server.format_metric(timer)
        self.assertIn('timer.key.lower 10', msg_timer)

        msg_gauge = server.format_metric(gauge)
        self.assertIn('gauge.key.gauge 5', msg_gauge)


if __name__ == '__main__':
    unittest.main()
