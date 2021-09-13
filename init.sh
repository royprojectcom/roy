rm -rf ./build ./dist ./.vagrant ./venv

python3 -m venv ./venv

source activate.sh

pip install --upgrade pip
pip install -e ".[dev]"
