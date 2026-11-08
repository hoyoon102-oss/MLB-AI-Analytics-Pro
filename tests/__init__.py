"""Keep the entire test process away from real favorites and settings."""
import atexit
import os
import tempfile

_previous_data_dir=os.environ.get('MLB_ANALYTICS_DATA_DIR')
_test_directory=tempfile.TemporaryDirectory(prefix='mlb-tests-')
os.environ['MLB_ANALYTICS_DATA_DIR']=_test_directory.name


def _restore_test_environment():
    if _previous_data_dir is None:
        os.environ.pop('MLB_ANALYTICS_DATA_DIR',None)
    else:
        os.environ['MLB_ANALYTICS_DATA_DIR']=_previous_data_dir
    _test_directory.cleanup()


atexit.register(_restore_test_environment)
