# Install notes

Install from the repository root, not from `src/dockhand`.

Recommended local-development install:

```bash
cd ~/projects/dockhand
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[test]"
dockhand --help
```

If you do not want a virtual environment:

```bash
cd ~/projects/dockhand
python3 -m pip install --user --upgrade pip setuptools wheel
python3 -m pip install --user -e .
```

If editable install fails because pip falls back to `setup.py develop`, remove stale legacy packaging files:

```bash
rm -f setup.py
rm -rf build dist *.egg-info src/*.egg-info
python3 -m pip install --user --upgrade pip setuptools wheel
python3 -m pip install --user -e .
```

The project intentionally does not include `setup.py`; editable installs should use modern PEP 660 behavior through `setuptools.build_meta`.
