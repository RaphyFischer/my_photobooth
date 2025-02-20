# install apt packages
sudo apt install -y python3 python3-pip
sudo apt-get -y install v4l-utils
sudo apt install -y gphoto2
sudo apt install -y libgphoto2-6 libxcb-cursor-dev
sudo apt install -y qtcreator qtbase5-dev qt5-qmake cmake
sudo apt install -y cups
sudo apt-get install -y printer-driver-gutenprint

# install python modules
pip install -r requirements.txt

# create desktop shortcut
sudo tee /usr/share/applications/photobooth.desktop  > /dev/null <<EOT
[Desktop Entry]
Name=MyPhotobooth
Exec=python $PWD/app.py -fullscreen
Icon=$PWD/ui/icons/aperature.png
Type=Application
Terminal=false
StartupWMClass=app.py
EOT

# build qt app
./build_qt.sh