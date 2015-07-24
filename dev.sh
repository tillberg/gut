set -e
rm gut
go build
GOMAXPROCS=`getconf _NPROCESSORS_ONLN` ./gut $*
