FROM python:3.14
WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# ── Cartopy / Natural Earth offline data ─────────────────────────────────────
# plots.py draws its maps from Natural Earth 110m physical features (ocean,
# land, coastline). By default cartopy downloads those shapefiles on first
# render, which would hang or fail in a network-restricted container. We seed
# them at build time into a fixed directory and point cartopy at it with
# CARTOPY_DATA_DIR (this is cartopy's read-only "pre_existing_data_dir"), so
# nothing is fetched at run time. Kept before `COPY . .` so it stays cached
# across code changes. Total payload: ~300 KB.
ENV CARTOPY_DATA_DIR=/code/.cartopy
RUN python -c "import cartopy, cartopy.io.shapereader as s; \
    from pathlib import Path; \
    d = Path('/code/.cartopy'); d.mkdir(parents=True, exist_ok=True); \
    cartopy.config['pre_existing_data_dir'] = d; \
    cartopy.config['data_dir'] = d; \
    cartopy.config['downloaders'][('shapefiles', 'natural_earth')].url_template = 'https://naturalearth.s3.amazonaws.com/{resolution}_{category}/ne_{resolution}_{name}.zip'; \
    [s.natural_earth(resolution='110m', category='physical', name=n) for n in ('ocean', 'land', 'coastline')]"

COPY . .

EXPOSE 8080

CMD ["shiny", "run", "src/shiny_app/app.py", "--host", "0.0.0.0", "--port", "8080"]
