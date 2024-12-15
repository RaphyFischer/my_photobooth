pyuic6 ui/mainwindow.ui -o MainWindow.py
pyside6-rcc -o resources_rc.py ui/resources.qrc
python3 app.py
