# your_app/management/commands/backfill_stock_clients.py
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum

from ...models import (
    Stock,
    StockMovement,
    Item,
    SizeQuantity,
    Order,
    ClientOrder,
    Client,
)


class Command(BaseCommand):
    help = (
        "Backfill Stock.client from source models:\n"
        " - Materials: Stock.content_object is Item -> client taken from Item.client (if field exists in DB)\n"
        " - Finished goods: Stock.content_object is SizeQuantity -> client resolved via "
        "   SizeQuantity.orders -> Order.client_order.client (uses most recent Order if multiple)\n"
        "Optionally also stamp StockMovement.client where NULL to the owning Stock.client."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Rows per transaction batch (default: 500)",
        )
        parser.add_argument(
            "--only-null",
            action="store_true",
            help="Only update Stock rows where client is NULL",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show intended changes without writing to DB",
        )
        parser.add_argument(
            "--update-movements",
            action="store_true",
            help="Also set StockMovement.client to Stock.client where it is currently NULL",
        )

    # -----------------------
    # Resolution helpers
    # -----------------------

    def resolve_client_for_item(self, item: Item):
        """
        Legacy materials path:
        If the Item still has a 'client' attribute/column in DB, use it.
        If not present or it's NULL, return None (the command won't error).
        """
        return getattr(item, "client", None)

    def resolve_client_for_sizequantity(self, sq: SizeQuantity):
        """
        Finished goods path:
        Resolve client via any linked Order -> ClientOrder -> Client.
        If multiple distinct clients appear (edge-case), choose the most recent Order.
        """
        # Use the M2M 'orders' on SizeQuantity; prefer latest order id
        orders_qs = (
            sq.orders.select_related("client_order__client")
            .order_by("-id")  # adjust if you have created_at
        )

        clients = []
        for o in orders_qs:
            co = getattr(o, "client_order", None)
            cl = getattr(co, "client", None) if co else None
            if cl:
                clients.append(cl)

        if not clients:
            return None

        unique_ids = {c.id for c in clients}
        if len(unique_ids) > 1:
            self.stdout.write(
                self.style.WARNING(
                    f"[warn] SizeQuantity id={sq.id} maps to multiple clients {sorted(unique_ids)}; "
                    f"using most recent order’s client id={clients[0].id}"
                )
            )
        return clients[0]

    def resolve_stock_client(self, stock: Stock):
        """
        Decide how to resolve client based on the stock's content_object type.
        """
        obj = stock.content_object
        if obj is None:
            return None

        # Rely on isinstance where models are available; also guard by content_type.model name
        model_name = stock.content_type.model  # lowercase ("item", "sizequantity", ...)
        if isinstance(obj, Item) or model_name == "item":
            return self.resolve_client_for_item(obj)

        if isinstance(obj, SizeQuantity) or model_name == "sizequantity":
            return self.resolve_client_for_sizequantity(obj)

        # Unknown: leave unchanged
        return None

    # -----------------------
    # Main
    # -----------------------

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        only_null = options["only_null"]
        dry_run = options["dry_run"]
        update_movements = options["update_movements"]

        qs = Stock.objects.all().select_related("content_type", "warehouse", "client")
        if only_null:
            qs = qs.filter(client__isnull=True)

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("No Stock rows to process."))
            return

        self.stdout.write(
            f"Processing {total} Stock rows (batch_size={batch_size}, dry_run={dry_run}, only_null={only_null}, update_movements={update_movements})"
        )

        processed = 0
        updated_stocks = 0
        updated_movs = 0

        # iterate in batches for memory safety
        while processed < total:
            batch = list(qs.order_by("id")[processed : processed + batch_size])

            if dry_run:
                for stock in batch:
                    new_client = self.resolve_stock_client(stock)
                    old_client = getattr(stock, "client", None)
                    if old_client != new_client:
                        self.stdout.write(
                            f"[dry-run] Stock id={stock.id} ({stock.content_type.model}#{stock.object_id}): "
                            f"client {getattr(old_client, 'id', None)} -> {getattr(new_client, 'id', None)}"
                        )
                        updated_stocks += 1
                processed += len(batch)
                continue

            with transaction.atomic():
                for stock in batch:
                    new_client = self.resolve_stock_client(stock)
                    old_client = getattr(stock, "client", None)

                    if old_client != new_client:
                        stock.client = new_client
                        stock.save(update_fields=["client"])
                        updated_stocks += 1

                        if update_movements:
                            # Stamp movements for this stock where client is NULL
                            mov_qs = StockMovement.objects.filter(stock=stock, client__isnull=True)
                            count = mov_qs.update(client=new_client)
                            updated_movs += count

            processed += len(batch)
            self.stdout.write(f"Processed {processed}/{total}…")

        msg = f"Done. Stocks updated: {updated_stocks}"
        if update_movements:
            msg += f"; StockMovements updated: {updated_movs}"
        self.stdout.write(self.style.SUCCESS(msg))
