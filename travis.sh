#/bin/sh
pushd $HOME

# LIRC
if [ ! `ls -A lirc` ]; then
    git clone git://git.code.sf.net/p/lirc/git lirc
    pushd lirc
    ./autogen.sh
    ./configure --prefix=$HOME/.local CFLAGS='-g -O2 -lrt' CXXFLAGS='-g -O2 -lrt'
    make
    popd
fi

pushd lirc
sudo make install
popd lirc

# SIP
if [ ! `ls -A sip-4.18` ]; then
    wget http://sourceforge.net/projects/pyqt/files/sip/sip-4.18/sip-4.18.tar.gz
    tar xzf sip-4.18.tar.gz
    pushd sip-4.18
    python configure.py
    make
    popd
fi

pushd sip-4.18
sudo make install
popd

# PyQt4
if [ ! `ls -A PyQt-x11-gpl-4.11.4` ]; then
    wget http://sourceforge.net/projects/pyqt/files/PyQt4/PyQt-4.11.4/PyQt-x11-gpl-4.11.4.tar.gz
    tar xzf PyQt-x11-gpl-4.11.4.tar.gz --keep-newer-files
    pushd PyQt-x11-gpl-4.11.4
    python configure.py -c --confirm-license --no-designer-plugin -e QtCore -e QtGui
    make
    popd
fi

pushd PyQt-x11-gpl-4.11.4
sudo make install
popd

popd
