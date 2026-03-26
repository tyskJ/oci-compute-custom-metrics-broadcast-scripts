#!/bin/bash

# Shell Options
# e : エラーがあったら直ちにシェルを終了
# u : 未定義変数を使用したときにエラーとする
# o : シェルオプションを有効にする
# pipefail : パイプラインの返り値を最後のエラー終了値にする (エラー終了値がない場合は0を返す)
set -euo pipefail

# Timezone
timedatectl set-timezone Asia/Tokyo
systemctl restart rsyslog

# Locale
dnf install -y langpacks-ja
localectl set-locale LANG=ja_JP.utf8
localectl set-keymap jp106

# Firewall Service disable
systemctl stop firewalld
systemctl disable firewalld
systemctl mask firewalld

# Nginx install
dnf install -y nginx
systemctl enable --now nginx

# SELinux disable
grubby --update-kernel ALL --args selinux=0
shutdown -r now