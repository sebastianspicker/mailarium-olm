"""CLI operational subcommand tests split from RF17."""

from __future__ import annotations

from src.cli import parse_args


class TestAnalyticsSubcommand:
    def test_analytics_stats(self) -> None:
        args = parse_args(["analytics", "stats"])
        assert args.subcommand == "analytics"
        assert args.analytics_action == "stats"

    def test_analytics_senders_default(self) -> None:
        args = parse_args(["analytics", "senders"])
        assert args.analytics_action == "senders"
        assert args.limit == 30

    def test_analytics_senders_custom(self) -> None:
        args = parse_args(["analytics", "senders", "50"])
        assert args.limit == 50

    def test_analytics_suggest(self) -> None:
        args = parse_args(["analytics", "suggest"])
        assert args.analytics_action == "suggest"

    def test_analytics_contacts(self) -> None:
        args = parse_args(["analytics", "contacts", "employee@example.test"])
        assert args.analytics_action == "contacts"
        assert args.email_address == "employee@example.test"

    def test_analytics_volume_default(self) -> None:
        args = parse_args(["analytics", "volume"])
        assert args.analytics_action == "volume"
        assert args.period == "month"

    def test_analytics_volume_week(self) -> None:
        args = parse_args(["analytics", "volume", "week"])
        assert args.period == "week"

    def test_analytics_entities(self) -> None:
        args = parse_args(["analytics", "entities"])
        assert args.analytics_action == "entities"
        assert args.entity_type is None

    def test_analytics_entities_with_type(self) -> None:
        args = parse_args(["analytics", "entities", "--type", "organization"])
        assert args.entity_type == "organization"

    def test_analytics_heatmap(self) -> None:
        args = parse_args(["analytics", "heatmap"])
        assert args.analytics_action == "heatmap"

    def test_analytics_response_times(self) -> None:
        args = parse_args(["analytics", "response-times"])
        assert args.analytics_action == "response-times"


class TestTrainingSubcommand:
    def test_training_generate_data(self) -> None:
        args = parse_args(["training", "generate-data", "output.jsonl"])
        assert args.subcommand == "training"
        assert args.training_action == "generate-data"
        assert args.output_path == "output.jsonl"

    def test_training_fine_tune(self) -> None:
        args = parse_args(["training", "fine-tune", "data.jsonl"])
        assert args.training_action == "fine-tune"
        assert args.data_path == "data.jsonl"
        assert args.output_dir == "models/fine-tuned"
        assert args.epochs == 3

    def test_training_fine_tune_custom(self) -> None:
        args = parse_args(
            [
                "training",
                "fine-tune",
                "data.jsonl",
                "--output-dir",
                "models/custom",
                "--epochs",
                "5",
            ]
        )
        assert args.output_dir == "models/custom"
        assert args.epochs == 5


class TestAdminSubcommand:
    def test_admin_reset_index_without_yes(self) -> None:
        args = parse_args(["admin", "reset-index"])
        assert args.subcommand == "admin"
        assert args.admin_action == "reset-index"
        assert args.yes is False

    def test_admin_reset_index_with_yes(self) -> None:
        args = parse_args(["admin", "reset-index", "--yes"])
        assert args.yes is True
