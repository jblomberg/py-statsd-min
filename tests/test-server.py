#!/usr/bin/env python
# -*- coding: utf-8 -*-


# Path hack.
import sys
import os
sys.path.insert(0, os.path.abspath('..'))

import server

import unittest

class ServerTestSuite(unittest.TestCase):
    '''StatsD server test cases'''
    def test_clean_key(self):
        key = server.clean_key('test key')
        self.assertEqual(key, 'test_key')

        key = server.clean_key('test/key')
        self.assertEqual(key, 'test-key')

        key = server.clean_key('test!key')
        self.assertEqual(key, 'testkey')

        key = server.clean_key('test.key')
        self.assertEqual(key, 'test.key')




if __name__ == '__main__':
    unittest.main()
