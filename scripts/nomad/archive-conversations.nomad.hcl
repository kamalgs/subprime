# Periodic batch job — archive the conversations table to CSV and truncate.
#
# Lives in this repo as a reference. Apply with:
#     nomad job run scripts/nomad/archive-conversations.nomad.hcl
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

    # Reuse the existing `finadvisor_data` host volume (declared in the
    # Nomad client config alongside the web app). Archives land under an
    # `archives/` subdir so they sit next to the app's other state.
    volume "finadvisor_data" {
      type      = "host"
      source    = "finadvisor_data"
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
        volume      = "finadvisor_data"
        destination = "/app/state"
        read_only   = false
      }

      env {
        SUBPRIME_ARCHIVE_DIR = "/app/state/archives"
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
