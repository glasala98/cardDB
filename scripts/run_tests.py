import unittest
import sys
import os

# Add root directory to path so tests can find modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def run_tests():
    loader = unittest.TestLoader()
    start_dir = 'tests'
    suite = loader.discover(start_dir)

    runner = unittest.TextTestRunner()
    result = runner.run(suite)

    if not result.wasSuccessful():
        sys.exit(1)

if __name__ == '__main__':
    run_tests()
