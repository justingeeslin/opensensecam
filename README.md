# OpenSenseCam
An open source, SenseCam implementation, built for Raspberry Pi.

## Install
Installs with a .deb file.

## Development

For rapid development, run `./dev-reinstall.sh` after each change. 

Other useful commands include:

### Compile a DEB file
From just outside the project folder run,
```dpkg-deb --root-owner-group --build app-sensecam/```
where `app-hello-world` is the name of the project folder.

### Install
When developing install the deb file this way:
```sudo apt install --reinstall  ./app-sensecam.deb```

### Running
Once installed, run it from the Pi Menu under Accessories. 

### Uninstall

```sudo apt remove opensensecam```