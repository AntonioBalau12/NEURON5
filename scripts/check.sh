#!/bin/sh
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
image=${1:-}
minutes=${MINUTES:-30}
work=$(mktemp -d)
name=hype-arena-check-$$
trap 'docker rm -f "$name" >/dev/null 2>&1 || true; rm -rf "$work"' EXIT

if [ -z "$image" ]; then
	image=hype-arena-check
	docker build --platform linux/amd64 -t "$image" "$root"
fi
user=$(docker image inspect "$image" --format '{{.Config.User}}')
case "${user%%:*}" in
"" | root | 0)
	echo "refused: the image's USER is '$user'; end the Dockerfile with USER 10001"
	exit 1
	;;
esac

mkdir -p "$work/universe" "$work/output"
python3 "$root/scripts/input.py" "$root/data/practice.csv" "$work/universe/universe.csv"
cp "$root/data/lexicon.json" "$work/universe/lexicon.json"
chmod 755 "$work/universe"
chmod 777 "$work/output"

deadline=$(($(date +%s) + minutes * 60))
docker run -d --name "$name" --platform linux/amd64 \
	--network none --read-only --user 10001:10001 \
	--cpus 2 --memory 6g --memory-swap 6g --pids-limit 256 \
	--cap-drop ALL --security-opt no-new-privileges \
	--tmpfs /tmp:rw,size=128m,mode=1777 \
	-v "$work/universe:/universe:ro" -v "$work/output:/output" \
	-e ARENA_DEADLINE="$deadline" \
	"$image" >/dev/null
echo "running $image for at most $minutes minutes"

while [ "$(docker inspect -f '{{.State.Running}}' "$name")" = true ]; do
	if [ "$(date +%s)" -ge "$deadline" ]; then
		echo "deadline: SIGTERM, and a kill 10 seconds later"
		docker stop -t 10 "$name" >/dev/null
		break
	fi
	sleep 2
done
docker logs --tail 20 "$name" 2>&1 | sed 's/^/  | /'
echo "exit code $(docker inspect -f '{{.State.ExitCode}}' "$name"), OOM killed: $(docker inspect -f '{{.State.OOMKilled}}' "$name")"

if [ -f "$work/output/output.csv" ]; then
	cp "$work/output/output.csv" "$root/output.csv"
	echo "saved $root/output.csv"
fi

python3 "$root/scripts/check_output.py" "$work/output" "$root/data/practice.csv" "$work/universe/universe.csv"
