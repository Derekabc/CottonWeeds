"""no random rotation"""
import csv
import argparse


def parse_args():
    parser = argparse.ArgumentParser(description='Train CottonWeed Classifier')
    parser.add_argument('--train_directory', type=str, required=False,
                        default='/home/dong9/PycharmProjects/CottonWeeds/DATASET', help="training directory")
    parser.add_argument('--model_name', type=str, required=False, default='alexnet',
                        help="choose a deep learning model")
    parser.add_argument('--train_mode', type=str, required=False, default='finetune',
                        help="Set training mode: finetune, transfer, scratch")
    parser.add_argument('--num_classes', type=int, required=False, default=15, help="Number of Classes")
    parser.add_argument('--seeds', type=int, required=False, default=0, help="random seed")
    parser.add_argument('--epochs', type=int, required=False, default=50, help="Training Epochs")
    parser.add_argument('--batch_size', type=int, required=False, default=12, help="Training batch size")
    parser.add_argument('--img_size', type=int, required=False, default=512, help="Image Size")
    parser.add_argument('--use_weighting', type=bool, required=False, default=False, help="use weighted cross entropy or not")
    args = parser.parse_args()
    return args


args = parse_args()
import torch, os
import random
import numpy as np
from sklearn.model_selection import KFold

# for reproducing
torch.manual_seed(args.seeds)
torch.cuda.manual_seed(args.seeds)
torch.cuda.manual_seed_all(args.seeds) # if you are using multi-GPU.
torch.backends.cudnn.benchmark = False
torch.backends.cudnn.deterministic = True
os.environ['PYTHONHASHSEED'] = str(args.seeds)
random.seed(args.seeds)
np.random.seed(args.seeds)


def seed_worker(worker_id):
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)
    random.seed(worker_seed)


g = torch.Generator()
g.manual_seed(args.seeds)


from torchvision import datasets, models, transforms
import torch.utils.data as data
from torch.utils.tensorboard import SummaryWriter
import torch.optim as optim
from torch.optim import lr_scheduler
import torch.nn as nn
from torchsummary import summary
import time, copy
import multiprocessing
import pretrainedmodels  # for inception-v4 and xception
from efficientnet_pytorch import EfficientNet


num_classes = args.num_classes
model_name = args.model_name
train_mode = args.train_mode
num_epochs = args.epochs
bs = args.batch_size
img_size = args.img_size
train_directory = args.train_directory

if not os.path.isfile('train_performance_cv.csv'):
    with open('train_performance_cv.csv', mode='w') as csv_file:
        fieldnames = ['Index', 'Model', 'Training Time', 'Trainable Parameters', 'Best Train Acc', 'Best Train Epoch',
                      'Best Val Acc', 'Best Val Epoch']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

# Set the model save path
if args.use_weighting:
    PATH = 'models_cv/' + model_name + "_" + str(args.seeds) + "_w" + ".pth"
else:
    PATH = 'models_cv/' + model_name + "_" + str(args.seeds) + ".pth"
# Number of workers
num_cpu = 32  # multiprocessing.cpu_count()

# Applying transforms to the data
# TODO: modify the normalization terms
image_transforms = {
    'train': transforms.Compose([
        transforms.RandomResizedCrop(size=img_size),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225])]),
    'valid': transforms.Compose([
        transforms.Resize(size=img_size),
        transforms.CenterCrop(size=img_size),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225])])}

# Load data from folders
dataset = datasets.ImageFolder(root=train_directory, transform=image_transforms['train'])
# Size of train and validation data
k_folds = 5
kfold = KFold(n_splits=k_folds, shuffle=True)

for fold, (train_idx,test_idx) in enumerate(kfold.split(dataset)):
    if not os.path.exists('models_cv/'):
        os.mkdir('models_cv/')

    # Set the model save path
    if args.use_weighting:
        print(True)
        PATH = 'models_cv/' + model_name + "_" + str(fold) + "_w" + ".pth"
    else:
        PATH = 'models_cv/' + model_name + "_" + str(fold) + ".pth"

    print('------------fold no---------{}----------------------'.format(fold))
    train_subsampler = torch.utils.data.SubsetRandomSampler(train_idx)
    test_subsampler = torch.utils.data.SubsetRandomSampler(test_idx)

    # Create iterators for data loading
    dataloaders = {
        'train': data.DataLoader(dataset, batch_size=bs, num_workers=num_cpu, pin_memory=True, drop_last=True,
                                 worker_init_fn=seed_worker, generator=g, sampler=train_subsampler),
        'valid': data.DataLoader(dataset, batch_size=bs, num_workers=num_cpu, pin_memory=True, drop_last=True,
                                 worker_init_fn=seed_worker, generator=g, sampler=test_subsampler)}

    # Class names or target labels
    class_names = dataset.classes
    print("Classes:", class_names)

    print("\nLoading pretrained-model for finetuning ...\n")
    model_ft = None

    if model_name == 'resnet18':
        # Modify fc layers to match num_classes
        model_ft = models.resnet18(pretrained=True)
        num_ftrs = model_ft.fc.in_features
        model_ft.fc = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'resnet50':
        # Modify fc layers to match num_classes
        model_ft = models.resnet50(pretrained=True)
        num_ftrs = model_ft.fc.in_features
        model_ft.fc = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'resnet101':
        # Modify fc layers to match num_classes
        model_ft = models.resnet101(pretrained=True)
        num_ftrs = model_ft.fc.in_features
        model_ft.fc = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'alexnet':
        model_ft = models.alexnet(pretrained=True)
        model_ft.classifier[6] = nn.Linear(4096, num_classes)
    elif model_name == 'vgg11':
        model_ft = models.vgg11(pretrained=True)
        model_ft.classifier[6] = nn.Linear(4096, num_classes)
    elif model_name == 'vgg16':
        model_ft = models.vgg16(pretrained=True)
        model_ft.classifier[6] = nn.Linear(4096, num_classes)
    elif model_name == 'vgg19':
        model_ft = models.vgg19(pretrained=True)
        model_ft.classifier[6] = nn.Linear(4096, num_classes)
    elif model_name == 'squeezenet':
        model_ft = models.squeezenet1_0(pretrained=True)
        model_ft.classifier[1] = nn.Conv2d(512, num_classes, kernel_size=(1, 1), stride=(1, 1))
    elif model_name == 'densenet121':
        model_ft = models.densenet121(pretrained=True)
        num_ftrs = model_ft.classifier.in_features
        model_ft.classifier = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'densenet169':
        model_ft = models.densenet169(pretrained=True)
        num_ftrs = model_ft.classifier.in_features
        model_ft.classifier = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'densenet161':
        model_ft = models.densenet161(pretrained=True)
        num_ftrs = model_ft.classifier.in_features
        model_ft.classifier = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'inception':
        model_ft = models.inception_v3(pretrained=True)
        model_ft.aux_logits = False
        # Handle the auxilary net
        num_ftrs = model_ft.AuxLogits.fc.in_features
        model_ft.AuxLogits.fc = nn.Linear(num_ftrs, num_classes)
        # Handle the primary net
        num_ftrs = model_ft.fc.in_features
        model_ft.fc = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'inceptionv4':
        model_ft = pretrainedmodels.inceptionv4(pretrained='imagenet')
        num_ftrs = model_ft.last_linear.in_features
        model_ft.last_linear = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'googlenet':
        model_ft = models.googlenet(pretrained=True)
        num_ftrs = model_ft.fc.in_features
        model_ft.fc = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'xception':
        model_ft = pretrainedmodels.xception(pretrained='imagenet')
        num_ftrs = model_ft.last_linear.in_features
        model_ft.last_linear = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'mobilenet_v2':
        model_ft = models.mobilenet_v2(pretrained=True)
        model_ft.classifier[1] = nn.Linear(model_ft.last_channel, num_classes)
    elif model_name == 'mobilenet_v3_small':
        model_ft = models.mobilenet_v3_small(pretrained=True)
        model_ft.classifier[3] = nn.Linear(model_ft.classifier[3].in_features, num_classes)
    elif model_name == 'mobilenet_v3_large':
        model_ft = models.mobilenet_v3_large(pretrained=True)
        model_ft.classifier[3] = nn.Linear(model_ft.classifier[3].in_features, num_classes)
    elif model_name == 'shufflenet_v2_x0_5':
        model_ft = models.shufflenet_v2_x0_5(pretrained=True)
        num_ftrs = model_ft.fc.in_features
        model_ft.fc = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'shufflenet_v2_x1_0':
        model_ft = models.shufflenet_v2_x1_0(pretrained=True)
        num_ftrs = model_ft.fc.in_features
        model_ft.fc = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'inceptionresnetv2':
        model_ft = pretrainedmodels.inceptionresnetv2(pretrained='imagenet')
        num_ftrs = model_ft.last_linear.in_features
        model_ft.last_linear = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'nasnetamobile':
        model_ft = pretrainedmodels.nasnetamobile(num_classes=1000, pretrained='imagenet')
        num_ftrs = model_ft.last_linear.in_features
        model_ft.last_linear = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'dpn68':
        model_ft = pretrainedmodels.dpn68(pretrained='imagenet')
        model_ft.last_linear = nn.Conv2d(832, num_classes, kernel_size=(1, 1), stride=(1, 1))
    elif model_name == 'polynet':
        model_ft = pretrainedmodels.polynet(num_classes=1000, pretrained='imagenet')
        num_ftrs = model_ft.last_linear.in_features
        model_ft.last_linear = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'mnasnet1_0':
        model_ft = models.mnasnet1_0(pretrained=True)
        num_ftrs = model_ft.classifier[1].in_features
        model_ft.classifier[1] = nn.Linear(num_ftrs, num_classes)
    elif model_name == 'efficientnet-b0':
        model_ft = EfficientNet.from_pretrained('efficientnet-b0', num_classes=num_classes)
    elif model_name == 'efficientnet-b1':
        model_ft = EfficientNet.from_pretrained('efficientnet-b1', num_classes=num_classes)
    elif model_name == 'efficientnet-b2':
        model_ft = EfficientNet.from_pretrained('efficientnet-b2', num_classes=num_classes)
    elif model_name == 'efficientnet-b3':
        model_ft = EfficientNet.from_pretrained('efficientnet-b3', num_classes=num_classes)
    elif model_name == 'efficientnet-b4':
        model_ft = EfficientNet.from_pretrained('efficientnet-b4', num_classes=num_classes)
    elif model_name == 'efficientnet-b5':
        model_ft = EfficientNet.from_pretrained('efficientnet-b5', num_classes=num_classes)
    elif model_name == 'efficientnet-b6':
        model_ft = EfficientNet.from_pretrained('efficientnet-b6', num_classes=num_classes)
    else:
        print("Invalid model name, exiting...")
        exit()

    # Set default device as gpu, if available
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model_ft = model_ft.to(device)

    # Print model summary
    print('Model Summary:-\n')
    for num, (name, param) in enumerate(model_ft.named_parameters()):
        print(num, name, param.requires_grad)
    if model_name == 'inception':
        summary(model_ft, input_size=(3, 299, 299))
    elif model_name == 'densenet121' or 'densenet161':
        pass
    else:
        summary(model_ft, input_size=(3, img_size, img_size))
    print(model_ft)

    # for class unbalance
    if args.use_weighting:
        # weights = np.array([762, 111, 254, 216, 1115, 273, 689, 129, 450, 129, 240, 234, 61, 72, 451])
        # weights = np.max(weights) / weights
        # class_weight = torch.FloatTensor(list(weights)).to(device)
        # weights = [1.75596, 10.045, 4.3898, 6.1944, 1.2, 4.90104, 1.94196, 8.6434, 2.97336, 10.37208, 4.6458, 4.765, 18.2787, 15.4861, 2.96676]  # 1.2 times
        weights = [2.04862, 10.045, 4.3898, 7.2268, 1.4, 5.71788, 2.26562, 8.6434, 3.46892, 12.10076, 4.6458, 4.765, 18.2787,	15.4861, 3.46122]  # 1.4 times
        class_weight = torch.FloatTensor(weights).to(device)
    else:
        weights = np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        class_weight = torch.FloatTensor(list(weights)).to(device)

    pytorch_total_params = sum(p.numel() for p in model_ft.parameters() if p.requires_grad)
    # print("Total parameters:", pytorch_total_params)
    # Loss function
    criterion = nn.CrossEntropyLoss(weight=class_weight)

    # Optimizer
    optimizer_ft = optim.SGD(model_ft.parameters(), lr=0.001, momentum=0.9)
    # Learning rate decay
    exp_lr_scheduler = lr_scheduler.StepLR(optimizer_ft, step_size=10, gamma=0.1)

    # Model training routine
    print("\nTraining:-\n")

    def train_model(model, criterion, optimizer, scheduler, num_epochs=50):
        since = time.time()

        best_model_wts = copy.deepcopy(model.state_dict())
        best_train_acc = 0.0
        best_train_epoch = 0
        best_val_epoch = 0
        best_val_acc = 0.0

        if args.use_weighting:
            # Tensorboard summary
            writer = SummaryWriter(log_dir=('./runs_cv/' + model_name + '_w' + '/' + str(fold)))
        else:
            writer = SummaryWriter(log_dir=('./runs_cv/' + model_name + '/' + str(fold)))

        for epoch in range(num_epochs):
            print('Epoch {}/{}'.format(epoch, num_epochs - 1))
            print('-' * 10)

            # Each epoch has a training and validation phase
            for phase in ['train', 'valid']:
                if phase == 'train':
                    model.train()  # Set model to training mode
                else:
                    model.eval()  # Set model to evaluate mode

                running_loss = 0.0
                running_corrects = 0

                # Iterate over data.
                for idx, (inputs, labels) in enumerate(dataloaders[phase]):
                    inputs = inputs.to(device, non_blocking=True)
                    labels = labels.to(device, non_blocking=True)

                    # zero the parameter gradients
                    optimizer.zero_grad()

                    # forward, track history if only in train
                    with torch.set_grad_enabled(phase == 'train'):
                        outputs = model(inputs)
                        _, preds = torch.max(outputs, 1)
                        loss = criterion(outputs, labels)

                        # backward + optimize only if in training phase
                        if phase == 'train':
                            loss.backward()
                            optimizer.step()

                    # statistics
                    running_loss += loss.item() * inputs.size(0)
                    running_corrects += torch.sum(preds == labels.data)
                if phase == 'train':
                    scheduler.step()

                epoch_loss = running_loss / ((idx + 1) * bs)
                epoch_acc = running_corrects.double() / ((idx + 1) * bs)

                print('{} Loss: {:.4f} Acc: {:.4f}'.format(
                    phase, epoch_loss, epoch_acc * 100))

                # Record training loss and accuracy for each phase
                if phase == 'train':
                    writer.add_scalar('Train/Loss', epoch_loss, epoch)
                    writer.add_scalar('Train/Accuracy', epoch_acc * 100, epoch)
                    writer.flush()
                    if epoch_acc > best_train_acc:
                        best_train_acc = epoch_acc
                        best_train_epoch = epoch
                else:
                    writer.add_scalar('Valid/Loss', epoch_loss, epoch)
                    writer.add_scalar('Valid/Accuracy', epoch_acc * 100, epoch)
                    writer.flush()

                # deep copy the model
                if phase == 'valid' and epoch_acc > best_val_acc:
                    best_val_acc = epoch_acc
                    best_model_wts = copy.deepcopy(model.state_dict())
                    best_val_epoch = epoch
            print()

        time_elapsed = time.time() - since

        with open('train_performance_cv.csv', 'a+', newline='') as write_obj:
            csv_writer = csv.writer(write_obj)
            csv_writer.writerow([fold, model_name, '{:.0f}m'.format(
                time_elapsed // 60), pytorch_total_params, '{:4f}'.format(best_train_acc.cpu().numpy() * 100),
                                 best_train_epoch, '{:4f}'.format(best_val_acc.cpu().numpy()  * 100), best_val_epoch])

        # load best model weights
        model.load_state_dict(best_model_wts)
        return model

    # Train the model
    model_ft = train_model(model_ft, criterion, optimizer_ft, exp_lr_scheduler,
                           num_epochs=num_epochs)
    # Save the entire model
    print("\nSaving the model...")
    torch.save(model_ft, PATH)
