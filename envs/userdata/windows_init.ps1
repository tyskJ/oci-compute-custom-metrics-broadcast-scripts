#ps1_sysnative

# Variables
$user='${instance_user}'
$password='${instance_password}'

# Change PW
Write-Output "Changing $user password"
net user $user $password
Write-Output "Changed $user password"