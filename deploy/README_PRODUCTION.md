# Production Setup (Nginx + Gunicorn + systemd)

## 1. Install packages

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
/home/ceexpii/scoring_system/venv_prod/bin/pip install gunicorn
```

## 2. Django prepare

Production reads its signing key from `/etc/scoring-system/secret-key` (or
`DJANGO_SECRET_KEY_FILE`). Create a random, production-only key before running
management commands. Keep the directory owned by `root:ceexpii` with mode `750`
and the file owned by `root:ceexpii` with mode `640`. Missing keys fail startup.
Do not use the development signing key or commit production secrets.
Rotating this key without fallbacks signs existing browser sessions out.

```bash
cd /home/ceexpii/scoring_system
/home/ceexpii/scoring_system/venv_prod/bin/python manage.py migrate --settings=scoring_system.settings_prod
/home/ceexpii/scoring_system/venv_prod/bin/python manage.py collectstatic --noinput --settings=scoring_system.settings_prod
```

## 3. Install systemd service

```bash
sudo cp deploy/systemd/scoring-system.service /etc/systemd/system/scoring-system.service
sudo systemctl daemon-reload
sudo systemctl enable --now scoring-system
sudo systemctl status scoring-system
```

## 4. Install nginx config

`/media/` must proxy to Django for authentication and object permissions. Only
the Nginx `internal` location `/_private_media/` may alias the media directory.
Never restore a public `/media/` alias. Sensitive APIs require server-side roles;
public password login and signup are disabled in production.

If enabling `/var/log/nginx/scoring-security.jsonl`, install
`deploy/logrotate/scoring-security` as `/etc/logrotate.d/scoring-security` and
keep the log at mode `640`, owned by `www-data:adm`. It records both the proxy
address and the unverified forwarded address without OAuth query parameters.

```bash
sudo cp deploy/nginx/scoring-system.conf /etc/nginx/sites-available/scoring-system
sudo ln -s /etc/nginx/sites-available/scoring-system /etc/nginx/sites-enabled/scoring-system
sudo nginx -t
sudo systemctl reload nginx
```

If default site is enabled and conflicts:

```bash
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

## 5. Enable HTTPS (Let's Encrypt)

```bash
sudo certbot --nginx -d ceexp.nu-tf-lab.jp
sudo certbot renew --dry-run
```

## 6. Deploy/update operation

```bash
cd /home/ceexpii/scoring_system
git pull
/home/ceexpii/scoring_system/venv_prod/bin/python manage.py migrate --settings=scoring_system.settings_prod
/home/ceexpii/scoring_system/venv_prod/bin/python manage.py collectstatic --noinput --settings=scoring_system.settings_prod
sudo systemctl restart scoring-system
sudo systemctl reload nginx
```

You can also run:

```bash
bash deploy/scripts/deploy_prod.sh
```

## 7. Logs

```bash
journalctl -u scoring-system -f
sudo tail -f /var/log/nginx/error.log
```

## 8. Branch and release workflow

See:

`deploy/README_WORKFLOW.md`
