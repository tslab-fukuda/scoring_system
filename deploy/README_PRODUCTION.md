# Production Setup (Nginx + Gunicorn + systemd)

## 1. Install packages

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
/home/ceexpii/scoring_system/venv_prod/bin/pip install gunicorn
```

## 2. Django prepare

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
