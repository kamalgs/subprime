# Periodic batch job — archive the conversations table to CSV and truncate.
#
# Lives in this repo as a reference. Apply with:
#     nomad job run docs/nomad/archive-conversations.nomad.hcl
#
# The image is the same finadvisor:<tag> we deploy the web app from; the
# `subprime maintenance archive-conversations` CLI subcommand ships in
# /usr/local/bin via the package install. Swap `latest` for the
# pinned-by-digest tag in your real deploy.

job "subprime-archive-conversations" {
  type = "batch"

  periodic {
    # Sunday 02:00 UTC, weekly. Adjust to taste.
    cron             = "0 2 * * 0"
    prohibit_overlap = true
    time_zone        = "UTC"
  }

  group "archive" {
    count = 1

    # Mount a host volume so the CSVs survive after the alloc exits.
    # Configure the corresponding `host_volume "subprime-archives" {...}`
    # block in the Nomad client config (or swap for a "csi" volume if
    # you've wired one up).
    volume "archives" {
      type      = "host"
      source    = "subprime-archives"
      read_only = false
    }

    task "archive" {
      driver = "docker"

      config {
        image   = "ghcr.io/kamalgs/finadvisor:latest"
        command = "subprime"
        args    = ["maintenance", "archive-conversations"]
      }

      volume_mount {
        volume      = "archives"
        destination = "/var/lib/subprime/archives"
        read_only   = false
      }

      env {
        SUBPRIME_ARCHIVE_DIR = "/var/lib/subprime/archives"
      }

      template {
        # Pull DATABASE_URL from Vault (or whatever secret store you use).
        # If your existing finadvisor deployment uses a different mechanism,
        # mirror that here.
        data = <<EOF
{{ with secret "secret/data/subprime/prod" }}
DATABASE_URL={{ .Data.data.database_url }}
{{ end }}
EOF
        destination = "secrets/db.env"
        env         = true
      }

      resources {
        cpu    = 200
        memory = 256
      }

      logs {
        max_files     = 5
        max_file_size = 5
      }
    }
  }
}
