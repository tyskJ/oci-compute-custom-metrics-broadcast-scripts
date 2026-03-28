Linux
=====================================================================
.. note::

  * ``root`` ユーザーにて実行します

1. ``Python`` & ``pip`` インストール
---------------------------------------------------------------------
.. code-block:: bash

  dnf install -y python3
  dnf install -y python3-pip

.. note::

  * ``python3 --version`` , ``pip3 --version`` でそれぞれバージョンが表示されればOK

2. 必要パッケージインストール
---------------------------------------------------------------------
.. code-block:: bash

  pip3 install --upgrade pip --root-user-action=ignore
  pip3 install oci --root-user-action=ignore

.. note::
  
  以下コマンドを実行して ``successfully`` がでればOK

.. code-block:: bash

  python3 - <<'EOF'
  import oci
  print("oci imported successfully")
  EOF

.. note::

  以下コマンドでインストール先が確認できます

.. code-block:: bash

  python3 - <<'EOF'
  import oci
  print(oci.__file__)
  EOF

3. 専用システムユーザー作成
---------------------------------------------------------------------
.. code-block:: bash

  useradd -s /sbin/nologin -M custom_agent

4. 設定ファイル作成
---------------------------------------------------------------------
`/etc/sysconfig/oci-custom-agent-linux <./envs/config/linux/oci-custom-agent-linux.json>`_

.. code-block:: bash

  chown root:custom_agent /etc/sysconfig/oci-custom-agent-linux
  chmod 640 /etc/sysconfig/oci-custom-agent-linux

5. スクリプトファイル作成
---------------------------------------------------------------------
.. code-block:: bash

  mkdir -p /opt/oci-custom-metrics
  
`/opt/oci-custom-metrics/oci_custom_agent_linux.py <./envs/config/linux/oci_custom_agent_linux.py>`_

.. code-block:: bash

  chown root:custom_agent /opt/oci-custom-metrics/oci_custom_agent_linux.py
  chmod 640 /opt/oci-custom-metrics/oci_custom_agent_linux.py

参考資料
=====================================================================
リファレンス
---------------------------------------------------------------------
* `oci <https://docs.oracle.com/en-us/iaas/tools/python/latest/>`_

ブログ
---------------------------------------------------------------------
* `systemd.timer 入門 <https://dev.classmethod.jp/articles/slug-btThPHViGsPt/>`_