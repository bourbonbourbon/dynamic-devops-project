# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
from flask import Flask
from version import __version__

app = Flask(__name__)

@app.route("/version")
def print_version():
    return __version__

if __name__ == "__main__":
    app.run(host="0.0.0.0")
