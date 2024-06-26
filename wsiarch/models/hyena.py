import os
import torch
import torch.nn as nn
import pytorch_lightning as pl
from wsiarch.models.components.hyena import HyenaOperator2D
from wsiarch.data.dataloaders import (
    FeatureImageDataset,
    create_data_loaders,
    FeatureImageDataModule,
)
from torchmetrics import Accuracy, F1Score, AUROC
from torch.optim.lr_scheduler import CosineAnnealingLR
from pytorch_lightning.loggers import TensorBoardLogger


# Define the HyenaModel
class HyenaModel(nn.Module):
    def __init__(
        self,
        d_model,
        num_classes,
        width_max,
        height_max,
        order=2,
        filter_order=64,
        dropout=0.0,
        filter_dropout=0.0,
    ):
        super(HyenaModel, self).__init__()
        
        self.d_model = d_model
        self.width_max = width_max
        self.height_max = height_max
        self.num_classes = num_classes
        self.order = order
        self.filter_order = filter_order
        self.dropout = dropout
        self.filter_dropout = filter_dropout

        self.hyena_layer = HyenaOperator2D(
            d_model=d_model,
            width_max=width_max,
            height_max=height_max,
            order=order,
            filter_order=filter_order,
            dropout=dropout,
            filter_dropout=filter_dropout,
        )

        self.maxpool = nn.AdaptiveMaxPool2d((1, 1))

        self.linear1 = nn.Linear(d_model, 1024)
        self.relu1 = nn.ReLU()

        self.linear2 = nn.Linear(1024, 512)
        self.relu2 = nn.ReLU()

        self.linear3 = nn.Linear(512, 256)
        self.relu3 = nn.ReLU()

        self.linear4 = nn.Linear(256, 128)
        self.relu4 = nn.ReLU()

        self.linear5 = nn.Linear(128, num_classes)

        self.loss_fn = nn.CrossEntropyLoss()

        self.train_accuracy = Accuracy(num_classes=num_classes, task="multiclass")
        self.val_accuracy = Accuracy(num_classes=num_classes, task="multiclass")
        self.test_accuracy = Accuracy(num_classes=num_classes, task="multiclass")

        self.train_f1 = F1Score(num_classes=num_classes, task="multiclass")
        self.val_f1 = F1Score(num_classes=num_classes, task="multiclass")
        self.test_f1 = F1Score(num_classes=num_classes, task="multiclass")

        self.train_auroc = AUROC(num_classes=num_classes, task="multiclass")
        self.val_auroc = AUROC(num_classes=num_classes, task="multiclass")
        self.test_auroc = AUROC(num_classes=num_classes, task="multiclass")

    def forward(self, x):
        height_x, width__x = x.shape[-2], x.shape[-1]
        x = self.hyena_layer(x)

        assert x.shape[-2] == self.height_max, f"{x.shape[-2]} != {self.height_max}"
        assert x.shape[-1] == self.width_max, f"{x.shape[-1]} != {self.width_max}"
        assert x.shape[1] == self.d_model, f"{x.shape[1]} != {self.d_model}"

        x = self.maxpool(x)
        x = torch.flatten(x, 1)

        assert x.shape[1] == self.d_model and len(x.shape) == 2, f"Shape of x is {x.shape}, should be (batch_size, d_model)"

        x = self.linear1(x)
        x = self.relu1(x)
        x = self.linear2(x)
        x = self.relu2(x)
        x = self.linear3(x)
        x = self.relu3(x)
        x = self.linear4(x)
        x = self.relu4(x)
        x = self.linear5(x)
        return x

    def compute_metrics(self, outputs, targets):
        accuracy = self.train_accuracy(outputs, targets)
        f1 = self.train_f1(outputs, targets)
        auroc = self.train_auroc(outputs, targets)
        return accuracy, f1, auroc

    def training_step(self, batch):
        x, y = batch
        outputs = self.forward(x)
        loss = self.loss_fn(outputs, y)
        accuracy, f1, auroc = self.compute_metrics(outputs, y)
        return loss, accuracy, f1, auroc

    def validation_step(self, batch):
        x, y = batch
        outputs = self.forward(x)
        loss = self.loss_fn(outputs, y)
        accuracy, f1, auroc = self.compute_metrics(outputs, y)
        return loss, accuracy, f1, auroc

    def test_step(self, batch):
        x, y = batch
        outputs = self.forward(x)
        loss = self.loss_fn(outputs, y)
        accuracy, f1, auroc = self.compute_metrics(outputs, y)
        return loss, accuracy, f1, auroc


class HyenaModelPL(pl.LightningModule):
    def __init__(
        self,
        d_model,
        num_classes,
        width_max,
        height_max,
        num_epochs=10,
        order=2,
        filter_order=64,
        dropout=0.0,
        filter_dropout=0.0,
    ):
        super().__init__()
        self.save_hyperparameters()

        self.hyena_layer = HyenaOperator2D(
            d_model=d_model,
            width_max=width_max,
            height_max=height_max,
            order=order,
            filter_order=filter_order,
            dropout=dropout,
            filter_dropout=filter_dropout,
        )

        # apply max pooling to the output of the Hyena layer
        self.maxpool = nn.AdaptiveMaxPool2d((1, 1))

        # Fully connected layers
        self.linear1 = nn.Linear(d_model, 1024)
        self.relu1 = nn.ReLU()

        self.linear2 = nn.Linear(1024, 512)
        self.relu2 = nn.ReLU()

        self.linear3 = nn.Linear(512, 256)
        self.relu3 = nn.ReLU()

        self.linear4 = nn.Linear(256, 128)
        self.relu4 = nn.ReLU()

        self.linear5 = nn.Linear(128, num_classes)

        # Metrics
        self.train_accuracy = Accuracy(num_classes=num_classes, task="multiclass")
        self.val_accuracy = Accuracy(num_classes=num_classes, task="multiclass")
        self.test_accuracy = Accuracy(num_classes=num_classes, task="multiclass")

        self.train_f1 = F1Score(num_classes=num_classes, task="multiclass")
        self.val_f1 = F1Score(num_classes=num_classes, task="multiclass")
        self.test_f1 = F1Score(num_classes=num_classes, task="multiclass")

        self.train_auroc = AUROC(num_classes=num_classes, task="multiclass")
        self.val_auroc = AUROC(num_classes=num_classes, task="multiclass")
        self.test_auroc = AUROC(num_classes=num_classes, task="multiclass")

        self.loss_fn = nn.CrossEntropyLoss()

    def forward(self, x):

        # what is the height and width of x?
        height_x, width__x = x.shape[-2], x.shape[-1]
        x = self.hyena_layer(x)

        # assert that x has shape (batch_size, d_model, height_max, width_max)
        assert (
            x.shape[-2] == self.hparams.height_max
        ), f"{x.shape[-2]} != {self.hparams.height_max}"
        assert (
            x.shape[-1] == self.hparams.width_max
        ), f"{x.shape[-1]} != {self.hparams.width_max}"
        assert (
            x.shape[1] == self.hparams.d_model
        ), f"{x.shape[1]} != {self.hparams.d_model}"

        x = self.maxpool(x)  # now x has shape (batch_size, d_model, 1, 1)

        # before passing x through the fully connected layers, we need to flatten it to shape (batch_size, d_model)
        x = torch.flatten(x, 1)

        assert (
            x.shape[1] == self.hparams.d_model and len(x.shape) == 2
        ), f"Shape of x is {x.shape}, should be (batch_size, d_model)"

        x = self.linear1(x)
        x = self.relu1(x)
        x = self.linear2(x)
        x = self.relu2(x)
        x = self.linear3(x)
        x = self.relu3(x)
        x = self.linear4(x)
        x = self.relu4(x)
        x = self.linear5(x)
        return x

    def training_step(self, batch, batch_idx):
        x, y = batch
        logits = self(x)
        loss = self.loss_fn(logits, y)
        self.log("train_loss", loss)
        self.log("train_accuracy", self.train_accuracy(logits, y))
        self.log("train_f1", self.train_f1(logits, y))
        self.log("train_auroc", self.train_auroc(logits, y))
        return loss

    def validation_step(self, batch, batch_idx):
        x, y = batch
        logits = self(x)
        loss = self.loss_fn(logits, y)
        self.log("val_loss", loss)
        self.log("val_accuracy", self.val_accuracy(logits, y))
        self.log("val_f1", self.val_f1(logits, y))
        self.log("val_auroc", self.val_auroc(logits, y))

    def test_step(self, batch, batch_idx):
        x, y = batch
        logits = self(x)
        loss = self.loss_fn(logits, y)
        self.log("test_loss", loss)
        self.log("test_accuracy", self.test_accuracy(logits, y))
        self.log("test_f1", self.test_f1(logits, y))
        self.log("test_auroc", self.test_auroc(logits, y))

    def on_train_epoch_end(self):
        # Log the current learning rate
        scheduler = self.lr_schedulers()
        current_lr = scheduler.get_last_lr()[0]
        self.log("lr", current_lr)

    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(self.parameters(), lr=0.001)
        scheduler = CosineAnnealingLR(
            optimizer, T_max=self.hparams.num_epochs, eta_min=0
        )
        return [optimizer], [scheduler]


# Main training loop
def train_model(data_dir, num_gpus=3, num_epochs=10):
    data_module = FeatureImageDataModule(
        root_dir=data_dir,
        metadata_file=os.path.join(data_dir, "metadata.csv"),
        width_max=230,
        height_max=445,
        batch_size=1,
        num_workers=9,
    )

    model = HyenaModelPL(
        d_model=2048,
        num_classes=2,
        num_epochs=10,
        width_max=230,
        height_max=445,
        order=2,
        filter_order=64,
        dropout=0.0,
        filter_dropout=0.0,
    )

    # Logger
    logger = TensorBoardLogger("lightning_logs", name="hyena")

    # Trainer configuration for distributed training
    trainer = pl.Trainer(
        max_epochs=num_epochs,
        logger=logger,
        devices=num_gpus,
        accelerator="gpu",  # 'ddp' for DistributedDataParallel
    )
    trainer.fit(model, data_module)
    trainer.test(model, data_module.test_dataloader())


if __name__ == "__main__":
    data_dir = "/media/hdd1/neo/LUAD-LUSC_FI"
    train_model(data_dir=data_dir)
