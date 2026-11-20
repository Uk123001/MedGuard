FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY lambda_function.py app.py ./
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT} -w 2 app:app"]
