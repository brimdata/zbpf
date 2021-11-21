$script = <<-SCRIPT
  echo "Provisioning..."
  apt update
  DEBIAN_FRONTEND=noninteractive apt -y dist-upgrade
  DEBIAN_FRONTEND=noninteractive apt install -y --install-recommends build-essential git make libelf-dev clang strace tar linux-headers-$(uname -r) gcc-multilib
  date > /etc/vagrant_provisioned_at
SCRIPT

Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/hirsute64"
  config.vm.provision "shell", inline: $script
  config.vm.network "forwarded_port", guest: 9867, host: 8098
end
