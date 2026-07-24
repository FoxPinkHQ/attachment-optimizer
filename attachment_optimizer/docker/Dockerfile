FROM odoo:18.0

USER root

# Install Python deps for S3 + MinIO client
RUN pip3 install --break-system-packages --no-cache-dir boto3 moto

# Create custom config
COPY docker/config/odoo.conf /etc/odoo/odoo.conf

USER odoo
