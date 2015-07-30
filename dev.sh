set -e
rm -f gut
go build
./gut $*
