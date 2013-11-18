git submodule init
git submodule update

npm install

# This fails on ubuntu, but whatever...
brew install libyaml

# These next two commands fail on OSX, but that's okay:
sudo apt-get install gettext libyaml-dev curl libcurl4-openssl-dev libexpat1-dev autoconf python-pip python-dev nodejs
sudo sysctl fs.inotify.max_user_watches=1048576


#echo 'kern.maxfiles=20480' | sudo tee -a /etc/sysctl.conf
#echo -e 'limit maxfiles 8192 20480\nlimit maxproc 1000 2000' | sudo tee -a /etc/launchd.conf
#echo 'ulimit -n 4096' | sudo tee -a /etc/profile

sudo pip install -r requirements.txt
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
