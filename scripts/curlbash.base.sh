#!/bin/bash
set -e
{
OS=$(uname -s | awk '{print tolower($0)}')
_ARCH=$(uname -m)
if [ "$_ARCH" = "x86_64" ]; then
    ARCH="amd64"
else
    ARCH="386"
fi
GUT_EXE="gut-__GUTVERSION__-$OS-$ARCH"
GUT_BUILD_TGZ="gut-v2.5.0-build-$OS-$ARCH.tgz"
CHECKSUMS=$(cat <<'EOF'
__CHECKSUMS__
EOF
);

cd /tmp
echo "Downloading and verifying checksum for $GUT_EXE.gz"
HASH=$(echo "$CHECKSUMS" | grep --color=never "$GUT_EXE.gz" | tr -s ' ' ' ' | cut -f 1 -d ' ')
rm -f "$GUT_EXE" "$GUT_EXE.gz"
wget -qO- "https://www.tillberg.us/c/$HASH/$GUT_EXE.gz" > "/tmp/$GUT_EXE.gz"
echo "$CHECKSUMS" | grep --color=never "$GUT_EXE.gz" | shasum -a256 -c-
echo "Checksum verified."
echo "Installing to /usr/local/bin/gut ..."
gzip -d "$GUT_EXE.gz"
chmod +x "$GUT_EXE"
set +e
mv "/tmp/$GUT_EXE" /usr/local/bin/gut
if [ $? -ne 0 ]; then
    set -e
    echo "Failed to move /tmp/$GUT_EXE to /usr/local/bin/gut"
    read -p "Shall I try to \"sudo mv /tmp/$GUT_EXE /usr/local/bin/gut\" (y/n)? " -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]
    then
        echo "OK. Trying again with sudo to install in /usr/local/bin/gut ..."
        sudo mv "/tmp/$GUT_EXE" /usr/local/bin/gut
    else
        echo "OK. To install manually, move /tmp/$GUT_EXE to somewhere in your PATH."
        exit
    fi
fi
echo "Installed successfully to /usr/local/bin/gut"
echo "Type \"gut sync\" for usage help, or visit https://www.github.com/tillberg/gut/"
}
