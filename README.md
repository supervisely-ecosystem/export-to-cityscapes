<div align="center" markdown>
<img src="https://i.imgur.com/zlpoZpK.png"/>

# From Supervisely to Cityscapes format


<p align="center">
  <a href="#Overview">Overview</a> •
  <a href="#Preparation">Preparation</a> •
  <a href="#How-To-Run">How To Run</a> •
  <a href="#How-To-Use">How To Use</a>
</p>

[![](https://img.shields.io/badge/slack-chat-green.svg?logo=slack)](https://supervise.ly/slack)
![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/supervisely-ecosystem/export-to-cityscapes)
[![views](https://app.supervise.ly/public/api/v3/ecosystem.counters?repo=supervisely-ecosystem/export-to-cityscapes&counter=views&label=views)](https://supervise.ly)
[![used by teams](https://app.supervise.ly/public/api/v3/ecosystem.counters?repo=supervisely-ecosystem/export-to-cityscapes&counter=downloads&label=used%20by%20teams)](https://supervise.ly)
[![runs](https://app.supervise.ly/public/api/v3/ecosystem.counters?repo=supervisely-ecosystem/export-to-cityscapes&counter=runs&label=runs&123)](https://supervise.ly)

</div>

## Overview

Converts [Supervisely](https://docs.supervise.ly/data-organization/00_ann_format_navi) project to [Cityscapes](https://github.com/mcordts/cityscapesScripts) format and prepares downloadable `tar` archive.

Supervisely project have to contain only classes with shapes `Polygon` or `Bitmap`. It means that all labeled objects have to be polygons or bitmaps. If your project has classes with other shapes and you would like to convert the shapes of these classes and all corresponding objects (e.g. rectangles to polygons), we recommend to use [`Convert Class Shape`](https://ecosystem.supervise.ly/apps/convert-class-shape) app. 



## Important notes

1) **Labeled foreground objects must never have holes**, i.e. if there is some background visible ‘through’ some foreground object, it is considered to 		be part of the foreground. If objects in Supervisely format have holes, after export to Cityscapes format holes will be sketched, so you may lose some 		of the input data.
<img src="https://i.imgur.com/AzgqBN8.png" width="600px"/>

2) If `Bitmap` in Supervisely format contain **not connected components**, after export to Cityscapes format, this figure will be split into several.
<p>
<img src="https://i.imgur.com/NxizXUE.png" width="400px"/>
<img src="https://i.imgur.com/vqGvmXo.png" width="400px"/>
</p>
3) Unlike the standard Cityscapes format, which can contain well-defined classes with well-defined colors and ids, project derived from Supervisely 		format can contain classes with **any names and colors**. In this regard:

- After export Supervisely project to Cityscapes format a file in `JSON` format will be added to the root of the resulting project with name `class_to_id.json`. It contains information about Supervisely project classes names, colors and their corresponding ids. 
- Annotation file with extension  `<image_name>_instanceIds.png` will not be created after conversion.



**Cityscapes dataset structure**

The folder structure of the Cityscapes dataset is as follows:

`{root}/{type}{video}/{split}/{city}/{city}_{seq:0>6}_{frame:0>6}_{type}{ext}`

The meaning of the individual elements is:

- `root` the root folder of the Cityscapes dataset.

- `type` the type/modality of data, e.g. gtFine for fine ground truth, or leftImg8bit for left 8-bit images.

- `split` the split, i.e. `train/val/test`. Note: not all kinds of data exist for all splits. Thus, do not be surprised to occasionally find empty folders.

- `city` location(city) where part of the dataset was recorded. In Supervisely project `city` is used as a dataset name.

You can download example of Cityscapes datasets [here](https://www.cityscapes-dataset.com/).

Current version of application supports only:
`gtFine` - the fine annotations. This type of annotations is used for validation, testing, and optionally for training. Annotations are encoded using json files containing the individual polygons.
`leftImg8bit` - the images. These are the standard annotated images.

In addition, Cityscapes format implies the presence of train/val datasets, and also train/val/test. Thus, to split images on training and validation datasets you should assign  corresponding tags (`train`, `val`, `test`) to images. If image doesn't have such tags, tags `train`, `val` and `test` will be assigned automatically, and user can define which percent of all images in project will be tagged as `train`, the rest images will be tagged as `val `and `test`.



## How To Run 
**Step 1**: Add app to your team from [Ecosystem](https://ecosystem.supervise.ly/apps/convert-supervisely-to-cityscapes-format) if it is not there.

**Step 2**: Open context menu of project -> `Download as` -> `Convert Supervisely to Cityscapes format` 

<img src="https://i.imgur.com/kxVGztq.png" width="600px"/>


## How to use
After running the application, you will be redirected to the Tasks page. Once application processing has finished, your link for downloading will become available. Click on the file name to download it

<img src="https://i.imgur.com/5WEh12e.png" width="800px"/>

**Note** You can also find your converted project in: Team Files->cityscapes_format->app_id->`projectId_projectName_formatName.tar`

<img src="https://i.imgur.com/5WEh12e.png" width="800px"/>
