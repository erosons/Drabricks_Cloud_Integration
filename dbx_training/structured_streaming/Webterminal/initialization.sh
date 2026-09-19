#!/bin/bash
sudo su
git clone https://github.com/dgadiraju/gen_logs.git

#Copy gen_logs directory to /opt - 
sudo mv -f gen_logs /opt

# Run change ownershio  
sudo chown -R `whoami` /opt/gen_logs

# Update PATH in .profile or .bash_profile or create soft links for the shell programs
export PATH=$PATH:/opt/gen_logs

# Either restart shell or run 
source ~/.profile && source ~/.bashrc

#Run start_logs.sh to start generating web logs
source /opt/gen_logs/start_logs.sh

# Run tail_logs.sh to preview while logs are being generated (Hit ctrl-c to come out)
# Run stop_logs.sh to stop generating web logs