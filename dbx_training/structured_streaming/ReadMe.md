# Simulating log genration  and pushing the log message to netcat Webserver

- Run the gen_log to generate the logs
- Lauch the Web terminal via UI or SSH
- Redirect tail command output to netcat server
- Validate that the log messages are being pushed to netcat server


# Netcat server Ships with all ubuntu distro

Validate on your ubuntu and since Data back launches Ubuntu same should work

   >> nc -l -9090    -> tested and Works

# Redirect tail command output to netcat server

/opt/gen_logs/tail_logs.sh|nc -l -p 9090

# To confirm that the NetCat server is getting stream  -like like real-life scenario of a busy webserver.

!telnet localhost 9090   

