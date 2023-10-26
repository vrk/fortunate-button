# fortunate-button

### RPI instructions

What to do when starting from a fresh raspberry pi lite install:

- Reset ssh keys so you can ssh in: `ssh-keygen -R <HOST>`
- `sudo apt update`
- `sudo apt upgrade`
- `sudo apt install vim git pip`
- [Set up GitHub ssh keys](https://gist.github.com/xirixiz/b6b0c6f4917ce17a90e00f9b60566278)
- Clone this repo
- cd into `fortunate-button`
- `python -m venv env` then install the missing thing
- `python -m venv env`
- `source env/bin/activate`
- `pip install --upgrade bleak`
- `pip install --upgrade Pillow RPi.GPIO gpiozero`
- `sudo apt-get install libopenjp2-7`
- [Start script on launch](https://learn.sparkfun.com/tutorials/how-to-run-a-raspberry-pi-program-on-startup#method-1-rclocal)
  - `sudo vim nano /etc/rc.local`
  - Add `sudo bash -c '/usr/bin/python3 /home/vrk/fortunate-button/fortune-pi.py > /home/pi/blink.log 2>&1' &` before exit

