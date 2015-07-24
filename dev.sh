set -e
rm -f gut
go build
GOMAXPROCS=`getconf _NPROCESSORS_ONLN` ./gut $*
