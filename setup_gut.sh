npm install

# This fails on ubuntu, but whatever...
brew install libyaml

# These next two commands fail on OSX, but that's okay:
sudo apt-get install gettext libyaml-dev curl libcurl4-openssl-dev libexpat1-dev autoconf python-pip python-dev nodejs
sudo sysctl fs.inotify.max_user_watches=1048576

pip install -r requirements.txt
git clone git://github.com/tillberg/git.git
cd git
make configure
./configure --prefix=/usr
make
sudo make install
cd ..
git clone git://github.com/tillberg/watchdog.git
cd watchdog
sudo python setup.py install
