"""Compatibility entry point: produces the same artifact the Flask app loads."""
from ml.alzheimer_model import train_new_model

if __name__ == '__main__':
    print(train_new_model()[1])
