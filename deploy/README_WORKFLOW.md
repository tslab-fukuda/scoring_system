# Workflow (feature -> test -> production)

## 1. Create feature branch and develop

```bash
cd /home/ceexpii/scoring_system
git checkout main
git pull --ff-only
git checkout -b feature/<topic>
```

After editing:

```bash
git add .
git commit -m "Implement <topic>"
git push -u origin feature/<topic>
```

## 2. Merge into main after review/test

```bash
git checkout main
git pull --ff-only
git merge --no-ff feature/<topic>
git push origin main
```

## 3. Deploy to test environment

```bash
cd /home/ceexpii/scoring_system
bash deploy/scripts/deploy_test.sh
```

## 4. Deploy to production environment

```bash
cd /home/ceexpii/scoring_system
bash deploy/scripts/deploy_prod.sh
```

## 5. Logs (production)

```bash
journalctl -u scoring-system -f
sudo tail -f /var/log/nginx/error.log
```
