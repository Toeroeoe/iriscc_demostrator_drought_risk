# Shiny Python Dashboard Template

A minimal, application-based template for building dashboards with Shiny for Python.

## Quick start

- Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- Run the app locally (from the project root):

```bash
# recommended: use the shiny runner
python -m shiny run app.py
```

- Or using the provided Makefile:

```bash
make install
make run
```

Docker (build and run):

```bash
docker build -t shiny-py-template .
docker run -p 8000:8000 shiny-py-template
```
## Access App

Then, open your browser and navigate to `http://localhost:8000` to access the app.

## Project layout

- `app/` - the Shiny application package
- `requirements.txt` - Python dependencies
- `Dockerfile` - image for containerized runs
- `Makefile` - helper tasks
- `README.md` - this file

## Next steps

- Replace `app/app.py` with your application logic.
- Add tests, CI, and more components as needed.
