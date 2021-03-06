"""
Partition dataset of images into training, validation and testing sets
"""
import os
from shutil import copyfile
import argparse
import math
import random
from os import walk


def iterate_dir(source, dest, ratio_list):
    # source = source.replace('\\', '/')
    # dest = dest.replace('\\', '/')

    for item in os.listdir(source):
        # generate train, val and test dataset
        train_dir = os.path.join(dest, 'train', item)
        val_dir = os.path.join(dest, 'val', item)
        test_dir = os.path.join(dest, 'test', item)
        if not os.path.exists(train_dir):
            os.makedirs(train_dir)
        if not os.path.exists(val_dir):
            os.makedirs(val_dir)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # get all the pictures in directory
        images = []
        ext = (".JPEG", "jpeg", "JPG", ".jpg", ".png", "PNG")
        for (dirpath, dirnames, filenames) in walk(os.path.join(source, item)):
            for filename in filenames:
                if filename.endswith(ext):
                    images.append(os.path.join(dirpath, filename))

        num_images = len(images)
        num_val_images = math.ceil(ratio_list[1] * num_images)
        num_test_images = math.ceil(ratio_list[2] * num_images)
        print("class", "total images", "n_train", "n_val", "n_test",
              item, num_images, (num_images - num_val_images - num_test_images), num_val_images, num_test_images)
        for j in range(num_val_images):
            idx = random.randint(0, len(images) - 1)
            filename = images[idx].split("/")[-1]
            copyfile(os.path.join(source, item, filename),
                     os.path.join(val_dir, filename))
            images.remove(images[idx])

        for i in range(num_test_images):
            idx = random.randint(0, len(images) - 1)
            filename = images[idx].split("/")[-1]
            copyfile(os.path.join(source, item, filename),
                     os.path.join(test_dir, filename))
            images.remove(images[idx])

        for file in images:
            filename = file.split("/")[-1]
            copyfile(os.path.join(source, item, filename),
                     os.path.join(train_dir, filename))


def main():
    # Initiate argument parser
    parser = argparse.ArgumentParser(description="Partition dataset of images into training and testing sets")
    parser.add_argument(
        '-i', '--imageDir',
        help='Path to the folder where the image dataset is stored. If not specified, the CWD will be used.',
        type=str,
        default='/home/dong9/Downloads/DATA_0820/Original_Data')
    parser.add_argument(
        '-o', '--outputDir',
        help='Path to the output folder where the train and test dirs should be created. '
             'Defaults to the same directory as IMAGEDIR.',
        type=str,
        default='/home/dong9/PycharmProjects/CottonWeeds/DATASET')
    parser.add_argument(
        '-r', '--ratio_list',
        help='The ratio of the number of test images over the total number of images. The default is 0.1.',
        default=[0.65, 0.2, 0.15],
        type=list)
    args = parser.parse_args()

    for i in range(5):
        random.seed(i)
        outputDir = args.outputDir + '/DATA_{}'.format(i)

        # Now we are ready to start the iteration
        iterate_dir(args.imageDir, outputDir, args.ratio_list)


if __name__ == '__main__':
    main()
