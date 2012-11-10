npm install
sudo apt-get install gettext
sudo pip install -r requirements.txt
sudo sysctl fs.inotify.max_user_watches=1048576
git clone git://github.com/tillberg/git.git
# sudo apt-get install curl libcurl4-openssl-dev libexpat1-dev gettext autoconf
cd git
make configure
./configure --prefix=/usr
make
sudo make install
cd ..
git clone git://github.com/tillberg/watchdog.git
sudo aptitude install libyaml-dev
cd watchdog
sudo python setup.py install
