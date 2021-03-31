import os
import numpy as np
import supervisely_lib as sly
from PIL import Image
from supervisely_lib.io.fs import get_file_name
from supervisely_lib.imaging.color import generate_rgb
from supervisely_lib.imaging.image import read, write
from supervisely_lib.io.fs import mkdir, copy_file, get_file_name
from supervisely_lib.io.json import load_json_file, dump_json_file



my_app = sly.AppService()

TEAM_ID = int(os.environ['context.teamId'])
WORKSPACE_ID = int(os.environ['context.workspaceId'])
PROJECT_ID = int(os.environ['modal.state.slyProjectId'])
ARCHIVE_NAME = 'Cityscapes.tar.gz'
RESULT_DIR_NAME = 'cityscapes_format'
#RESULT_SUBDIR_NAME = 'VOCdevkit/VOC'
images_dir_name = 'leftImg8bit'
annotations_dir_name = 'gtFine'

#ann_obj_class_dir_name = 'SegmentationObject'
#trainval_sets_dir_name = 'ImageSets'
#trainval_sets_subdir_name = 'Segmentation'
#train_txt_name = 'train.txt'
#val_txt_name = 'val.txt'
#pascal_contour = 0
#pascal_contour_color = [192, 224, 224]
#pascal_ann_ext = '.png'
#pascal_contour_name = 'pascal_contour'
#train_val_split_coef = 4 / 5


#if train_val_split_coef > 1 or train_val_split_coef < 0:
#    raise ValueError('train_val_split_coef should be between 0 and 1, your data is {}'.format(train_val_split_coef))



def from_ann_to_pascal_mask(ann, palette, name_to_index, pascal_contour):
    mask = np.zeros((ann.img_size[0], ann.img_size[1], 3), dtype=np.uint8)
    for label in ann.labels:
        label.geometry.draw(mask, name_to_index[label.obj_class.name])
        if pascal_contour != 0:
            label.geometry.draw_contour(mask, name_to_index[pascal_contour_name], pascal_contour)
    mask = mask[:, :, 0]
    pascal_mask = Image.fromarray(mask).convert('P')
    pascal_mask.putpalette(np.array(palette, dtype=np.uint8))

    return pascal_mask


def from_ann_to_obj_class_mask(ann, palette, pascal_contour):
    exist_colors = palette[: -1]
    need_colors = len(ann.labels) - len(exist_colors) + 1
    for _ in range(need_colors):
        new_color = generate_rgb(exist_colors)
        exist_colors.append(new_color)

    mask = np.zeros((ann.img_size[0], ann.img_size[1], 3), dtype=np.uint8)
    for idx, label in enumerate(ann.labels):
        label.geometry.draw(mask, idx + 1)
        if pascal_contour != 0:
            label.geometry.draw_contour(mask, len(exist_colors), pascal_contour)

    if pascal_contour != 0:
        exist_colors.append(palette[-1])
    mask = mask[:, :, 0]
    pascal_mask = Image.fromarray(mask).convert('P')
    pascal_mask.putpalette(np.array(exist_colors, dtype=np.uint8))

    return pascal_mask


@my_app.callback("from_sl_to_cityscapes")
@sly.timeit
def from_sl_to_cityscapes(api: sly.Api, task_id, context, state, app_logger):

    meta_json = api.project.get_meta(PROJECT_ID)
    meta = sly.ProjectMeta.from_json(meta_json)


    RESULT_ARCHIVE = os.path.join(my_app.data_dir, ARCHIVE_NAME)
    RESULT_DIR = os.path.join(my_app.data_dir, RESULT_DIR_NAME)
    result_images_dir = os.path.join(RESULT_DIR, images_dir_name)
    result_annotations_dir = os.path.join(RESULT_DIR, annotations_dir_name)
    sly.fs.mkdir(result_images_dir)
    sly.fs.mkdir(result_annotations_dir)
    app_logger.info("Make Cityscapes format dirs")

    name2id = {}
    for idx, obj_class in enumerate(meta.obj_classes):
        name2id[obj_class.name] = (idx + 1, idx + 1, idx + 1)

    app_logger.info("Create palette") #TODO Is need to print palette?


    datasets = api.dataset.get_list(PROJECT_ID)
    for dataset in datasets:
        progress = sly.Progress('Convert images and anns from dataset {}'.format(dataset.name), len(datasets), app_logger)
        images_dir_path = os.path.join(result_images_dir, dataset.name)
        annotations_dir_path = os.path.join(result_annotations_dir, dataset.name)
        mkdir(images_dir_path)
        mkdir(annotations_dir_path)

        images = api.image.get_list(dataset.id)
        for batch in sly.batched(images):
            image_ids = [image_info.id for image_info in batch]
            image_names = [image_info.name for image_info in batch]
            image_paths = [os.path.join(images_dir_path, image_name) for image_name in image_names]
            api.image.download_paths(dataset.id, image_ids, image_paths)

            ann_infos = api.annotation.download_batch(dataset.id, image_ids)
            anns = [sly.Annotation.from_json(ann_info.annotation, meta) for ann_info in ann_infos]


            mask_color = np.zeros((ann.img_size[0], ann.img_size[1], 3), dtype=np.uint8)
            mask_label = np.zeros((ann.img_size[0], ann.img_size[1], 3), dtype=np.uint8)
            poly_json = {'imgHeight': ann.img_size[0], 'imgWidth': ann.img_size[1], 'objects': []}
            for label in ann.labels:
                label.geometry.draw(mask_color, label.obj_class.color)
                label.geometry.draw(mask_label, name2id[label.obj_class.name])
                contours = label.geometry.to_contours()[0]
                poly_json['objects'].append({'label': label.obj_class.name, 'polygon': contours.exterior_np.tolist()})

            dump_json_file(poly_json, os.path.join(annotations_dir_path, get_file_name(image_name) + '_polygons.json'))
            write(os.path.join(annotations_dir_path, get_file_name(image_name) + '_color.png'), mask_color)
            write(os.path.join(annotations_dir_path, get_file_name(image_name) + '_labelIds.png'), mask_label)





    datasets = api.dataset.get_list(PROJECT_ID)
    for dataset in datasets:
        progress = sly.Progress('Convert images and anns from dataset {}'.format(dataset.name), len(datasets), app_logger)
        images = api.image.get_list(dataset.id)
        for batch in sly.batched(images):
            image_ids = [image_info.id for image_info in batch]
            image_names = [image_info.name for image_info in batch]
            image_paths = [os.path.join(result_images_dir, image_name) for image_name in image_names]
            api.image.download_paths(dataset.id, image_ids, image_paths)

            ann_infos = api.annotation.download_batch(dataset.id, image_ids)
            anns = [sly.Annotation.from_json(ann_info.annotation, meta) for ann_info in ann_infos]
            for idx, ann in enumerate(anns):
                pascal_mask = from_ann_to_pascal_mask(ann, palette, name_to_index, pascal_contour)
                pascal_mask.save(os.path.join(result_annotations_dir, image_names[idx].split('.')[0] + pascal_ann_ext))

                pascal_obj_class_mask = from_ann_to_obj_class_mask(ann, palette, pascal_contour)
                pascal_obj_class_mask.save(os.path.join(result_object_classes_dir, image_names[idx].split('.')[0] + pascal_ann_ext))

        progress.iter_done_report()

    all_image_names = [get_file_name(im_name) for im_name in os.listdir(result_images_dir)]
    with open(os.path.join(result_trainval_subdir, 'trainval.txt'), 'w') as f:
        f.writelines(line + '\n' for line in all_image_names)
    with open(os.path.join(result_trainval_subdir, 'train.txt'), 'w') as f:
        train_length = int(len(all_image_names) * train_val_split_coef)
        f.writelines(line + '\n' for line in all_image_names[:train_length])
    with open(os.path.join(result_trainval_subdir, 'val.txt'), 'w') as f:
        f.writelines(line + '\n' for line in all_image_names[train_length:])

    sly.fs.archive_directory(RESULT_DIR, RESULT_ARCHIVE)
    app_logger.info("Result directory is archived")

    upload_progress = []
    remote_archive_path = "/pascal_format/{}/{}".format(task_id, ARCHIVE_NAME)

    def _print_progress(monitor, upload_progress):
        if len(upload_progress) == 0:
            upload_progress.append(sly.Progress(message="Upload {!r}".format(ARCHIVE_NAME),
                                                total_cnt=monitor.len,
                                                ext_logger=app_logger,
                                                is_size=True))
        upload_progress[0].set_current_value(monitor.bytes_read)

    file_info = api.file.upload(TEAM_ID, RESULT_ARCHIVE, remote_archive_path, lambda m: _print_progress(m, upload_progress))
    app_logger.info("Uploaded to Team-Files: {!r}".format(file_info.full_storage_url))
    api.task.set_output_archive(task_id, file_info.id, ARCHIVE_NAME, file_url=file_info.full_storage_url)


    my_app.stop()



def main():
    sly.logger.info("Script arguments", extra={
        "TEAM_ID": TEAM_ID,
        "WORKSPACE_ID": WORKSPACE_ID,
        "PROJECT_ID": PROJECT_ID
    })

    # Run application service
    my_app.run(initial_events=[{"command": "from_sl_to_cityscapes"}])



if __name__ == '__main__':
        sly.main_wrapper("main", main)