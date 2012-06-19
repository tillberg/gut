npm install
pip install -r requirements.txt
git clone git://github.com/tillberg/git.git
# sudo apt-get install curl libcurl4-openssl-dev libexpat1-dev gettext
cd git
make configure
./configure --prefix=/usr
make
sudo make install
