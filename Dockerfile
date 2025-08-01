FROM python:3.11-slim

WORKDIR /app

# ��������� �����������
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# �������� ��������� � �������
COPY . .

# �������� ����� ��� ������ � ����� (���� �� �����������)
RUN mkdir -p /data /config /templates

# ��������� ���� (�� ��������� 8080)
EXPOSE 8080

CMD ["python", "main.py"]