docker compose up -d --build
python -m pytest ./backend/tests/integration
docker compose rm -sf
read -p "Press any key to continue..." x