set -e
go build
GOMAXPROCS=`getconf _NPROCESSORS_ONLN` ./gut $*
