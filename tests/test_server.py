#!/usr/bin/env python
# -*- coding: utf-8 -*-


# Path hack.
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import server

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
        self.assertEqual(metric, (('test.key', 1.0, 'c', 0.1)))

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

    def test_process_lines(self):
        lines = [
            'test.key: 1|c\n',
            'badline',
            'test.key: 2|c\n',
            'test.key2: 20|ms\n',
            ]
        server.process_lines(lines)
        self.assertEqual(server.metrics['c']['test.key'], [1.0, 2.0])
        self.assertEqual(server.metrics['ms']['test.key2'], [20.0])


if __name__ == '__main__':
    unittest.main()
