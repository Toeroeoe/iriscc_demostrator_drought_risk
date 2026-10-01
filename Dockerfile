FROM python:3.12
WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY . .

EXPOSE 8080

CMD ["shiny", "run", "src/shiny_app/app.py", "--host", "0.0.0.0", "--port", "8080"]
