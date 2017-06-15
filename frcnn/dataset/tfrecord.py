import sonnet as snt
import tensorflow as tf
import numpy as np
import os

from .dataset import Dataset


class TFRecordDataset(Dataset):

    def __init__(self, name='tfrecord_dataset', **kwargs):
        super(TFRecordDataset, self).__init__(name=name, **kwargs)

        self._context_features = {
            'image_raw': tf.FixedLenFeature([], tf.string),
            'filename': tf.FixedLenFeature([], tf.string),
            'width': tf.FixedLenFeature([], tf.int64),
            'height': tf.FixedLenFeature([], tf.int64),
            'depth': tf.FixedLenFeature([], tf.int64),
        }

        self._sequence_features = {
            'label': tf.VarLenFeature(tf.int64),
            'xmin': tf.VarLenFeature(tf.int64),
            'xmax': tf.VarLenFeature(tf.int64),
            'ymin': tf.VarLenFeature(tf.int64),
            'ymax': tf.VarLenFeature(tf.int64),
        }

    def _build(self):
        """Returns a tuple containing image, image metadata and label."""

        split_path = os.path.join(
            self._dataset_dir, f'{self._subset}.tfrecords'
        )

        filename_queue = tf.train.string_input_producer(
            [split_path], num_epochs=self._num_epochs
        )

        reader = tf.TFRecordReader()
        _, raw_record = reader.read(filename_queue)

        # We parse variable length features (bboxes in a image) as sequence
        # features
        context_example, sequence_example = tf.parse_single_sequence_example(
            raw_record,
            context_features=self._context_features,
            sequence_features=self._sequence_features
        )

        # TODO: The fact that it's a JPEG file should also be in `voc.py`.
        # TODO: Images are around ~500 pixels, should resize first when decoding?
        # Decode and preprocess the example (crop, adjust mean and variance).
        # image_jpeg = tf.decode_raw(example['image_raw'], tf.string)
        image_raw = tf.image.decode_jpeg(context_example['image_raw'])
        tf.summary.image('image_raw', image_raw, max_outputs=20)

        image = tf.image.per_image_standardization(image_raw)
        height = tf.cast(context_example['height'], tf.int32)
        width = tf.cast(context_example['width'], tf.int32)
        image_shape = tf.stack([height, width, 3])
        image = tf.reshape(image, image_shape)

        label = self.sparse_to_tensor(sequence_example['label'])
        xmin = self.sparse_to_tensor(sequence_example['xmin'])
        xmax = self.sparse_to_tensor(sequence_example['xmax'])
        ymin = self.sparse_to_tensor(sequence_example['ymin'])
        ymax = self.sparse_to_tensor(sequence_example['ymax'])

        bboxes = tf.stack([xmin, ymin, xmax, ymax, label], axis=1)

        queue = tf.RandomShuffleQueue(
            capacity=100,
            min_after_dequeue=20,
            dtypes=[tf.float32, tf.int32],
            names=['image', 'bboxes'],
            name='tfrecord_queue'
        )

        enqueue_ops = [queue.enqueue({
            'image': image,
            'bboxes': bboxes
        })] * 4

        tf.train.add_queue_runner(tf.train.QueueRunner(queue, enqueue_ops))

        return queue.dequeue()

    def sparse_to_tensor(self, sparse_tensor, dtype=tf.int32, axis=[1]):
        return tf.squeeze(
            tf.cast(tf.sparse_tensor_to_dense(sparse_tensor), dtype), axis=axis
        )
