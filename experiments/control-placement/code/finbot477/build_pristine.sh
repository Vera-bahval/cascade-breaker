#!/bin/zsh
# Собирает чистую базу профиля поставщика с хуками на заданный порт: ./build_pristine.sh <A–F> <port>
# Результат: code/finbot477/pristine/pristine_<prof>_<port>.db (в гит не класть).
HERE=${0:A:h}; FB=${HERE:h:h}/finbot-pr477; PROF=$1; PORT=$2
mkdir -p $HERE/pristine; cd $FB
TMP=build_${PROF}_${PORT}.db; rm -f $TMP $TMP-wal $TMP-shm
export DATABASE_URL=sqlite://$TMP
.venv/bin/python scripts/db.py setup > /dev/null 2>&1 || { echo "db setup failed"; exit 1; }
.venv/bin/python $HERE/seed_profile.py $PROF $PORT || exit 1
sqlite3 $TMP "pragma wal_checkpoint(TRUNCATE);" > /dev/null
mv $TMP $HERE/pristine/pristine_${PROF}_${PORT}.db; rm -f $TMP-wal $TMP-shm
echo "pristine_${PROF}_${PORT}.db"
