#! /usr/bin/python
import os

if not os.getcwd().endswith('exp3'):
    os.chdir('exp3')

import sys
import random
import gc
import numpy as np
from scipy import misc

sys.path.append("../lib")
import NN_Model
import FileIO
import MapSwipe
import Parameters

sys.path.append("../exp2")
import DL_OSM_MS

sample_dir = '../samples0/'


def active_sampling(m0, act_n):
    client = MapSwipe.MSClient()
    MS_train_p = client.MS_train_positive()
    MS_train_n = client.MS_train_negative()
    task_w = FileIO.osm_building_weight();

    MS_train_n = list(set(MS_train_n).difference(set(task_w.keys())))
    if len(MS_train_n) < act_n / 2:
        print 'act_n/2 is larger than MS_train_n size '
        print 'act_n is set to %d' % len(MS_train_n) * 2
        act_n = len(MS_train_n) * 2
    negative_img_X = np.zeros((act_n / 2, 256, 256, 3))
    for i, img in enumerate(MS_train_n[-act_n/2:]):
        negative_img_X[i] = misc.imread(os.path.join(sample_dir, 'train/MS_record/', img))
    label_n = np.zeros((act_n / 2, 2))
    label_n[:, 0] = 1

    MS_diff_OSM_train_p = list(set(MS_train_p).difference(set(task_w.keys())))
    print 'MS_diff_OSM_train_p: %d' % len(MS_diff_OSM_train_p)

    img_X = np.zeros((len(MS_diff_OSM_train_p), 256, 256, 3))
    for i, img in enumerate(MS_diff_OSM_train_p):
        img_X[i] = misc.imread(os.path.join(sample_dir, 'train/MS_record/', img))

    m0.set_prediction_input(img_X)
    scores, _ = m0.predict()

    indexes = np.where((scores < 0.6) & (scores > 0.4))[0]
    if indexes.shape[0] < act_n / 2:
        print 'act_n/2 is larger than uncertain samples'
        print 'act_n is set to %d' % indexes.shape[0] * 2
        act_n = indexes.shape[0] * 2
    uncertain_img_X = img_X[indexes]
    j = range(indexes.shape[0])
    random.shuffle(j)
    positive_img_X = uncertain_img_X[j][0:act_n / 2]

    label_p = np.zeros((act_n / 2, 2))
    label_p[:, 1] = 1


    return np.concatenate((negative_img_X, positive_img_X)), np.concatenate((label_n, label_p))


if __name__ == '__main__':
    evaluate_only, external_test, tr_n1, tr_n0, tr_b, tr_e, tr_t, te_n, nn, act_n = Parameters.deal_args(
        sys.argv[1:])

    print '--------------- Read Samples ---------------'
    img_X, Y = DL_OSM_MS.read_train_sample(tr_n1, tr_n0)

    if not evaluate_only:
        print '--------------- M0: Training on OSM Labels---------------'
        m = NN_Model.Model(img_X, Y, nn + '_active_jy')
        m.set_batch_size(tr_b)
        m.set_epoch_num(tr_e)
        m.set_thread_num(tr_t)
        m.train(nn)
        print '--------------- M0: Evaluation on Training Samples ---------------'
        m.evaluate()

        print '--------------- Ma: Actively Sampling ---------------'
        img_Xa, Ya = active_sampling(m, act_n)
        img_X = np.concatenate((img_X, img_Xa))
        Y = np.concatenate((Y, Ya))
        index = range(img_X.shape[0])
        random.shuffle(index)
        img_X = img_X[index]
        Y = Y[index]

        print '--------------- Ma: Re-Training ---------------'
        m.set_XY(img_X, Y)
        m.re_learn()
        print '--------------- Ma: Evaluation on Training Samples ---------------'
        m.evaluate()
    else:
        m = NN_Model.Model(img_X, Y, nn + '_active_jy')

    del img_X, Y
    gc.collect()

    print '--------------- Ma: Evaluation on Validation Samples ---------------'
    img_X2, Y2 = FileIO.read_valid_sample(te_n)
    m.set_evaluation_input(img_X2, Y2)
    m.evaluate()
    del img_X2, Y2
    gc.collect()

    if external_test:
        print '--------------- Ma: Evaluation on Expert  Labeled Samples ---------------'
        img_X3, Y3 = FileIO.read_external_test_sample()
        m.set_evaluation_input(img_X3, Y3)
        m.evaluate(True)
        del img_X3, Y3
        gc.collect()
