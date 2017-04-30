#! /usr/bin/python
import sys
import os
import time
import random
import gc
import numpy as np
from scipy import misc

sys.path.append("../lib")
import NN_Model
import FileIO
import MapSwipe
import Parameters


def osm_building_weight():
    task_w = {}
    osm_buildings = FileIO.csv_reader("../data/buildings.csv")
    for row in osm_buildings:
        task_x = row['task_x']
        task_y = row['task_y']
        k = '%s-%s' % (task_x, task_y)
        task_w[k] = 1
    return task_w


def read_test_sample(n, test_imgs, ms_p_imgs, ms_n_imgs):
    img_X = np.zeros((n, 256, 256, 3))
    label = np.zeros((n, 2))
    img_dir1 = '../data/image_project_922/'
    img_dir2 = '../data/image_project_922_negative/'
    random.shuffle(test_imgs)
    i = 0
    te_p, te_n = 0, 0
    for img in test_imgs:
        if i >= n:
            break
        if os.path.exists(os.path.join(img_dir1, img)):
            img_X[i] = misc.imread(os.path.join(img_dir1, img))
        else:
            img_X[i] = misc.imread(os.path.join(img_dir2, img))
        i1, i2 = img.index('-'), img.index('.')
        task_x, task_y = img[0:i1], img[(i1 + 1):i2]
        if [int(task_x), int(task_y)] in ms_p_imgs:
            label[i, 1] = 1
            i += 1
            te_p += 1
        elif [int(task_x), int(task_y)] in ms_n_imgs:
            label[i, 0] = 1
            i += 1
            te_n += 1
    print 'positive testing samples: %d \n ' % te_p
    print 'negative testing samples: %d \n ' % te_n
    return img_X, label


def read_train_sample(n1, n0, train_imgs, ms_n_imgs):
    img_X1, img_X0 = np.zeros((n1, 256, 256, 3)), np.zeros((n0, 256, 256, 3))
    label = np.zeros((n1 + n0, 2))

    task_w = osm_building_weight();
    img_dir1 = '../data/image_project_922/'
    img_dir2 = '../data/image_project_922_negative/'
    p_imgs, n_imgs = [], []
    for img in train_imgs:
        i1, i2 = img.index('-'), img.index('.')
        task_x, task_y = img[0:i1], img[(i1 + 1):i2]
        k = '%s-%s' % (task_x, task_y)
        if task_w.has_key(k):
            p_imgs.append(img)
        elif [int(task_x), int(task_y)] in ms_n_imgs:
            n_imgs.append(img)

    print 'p_imgs labeled by OSM: %d \n' % len(p_imgs)
    print 'n_imgs labeled by MS: %d \n' % len(n_imgs)

    p_imgs = random.sample(p_imgs, n1)
    for i, img in enumerate(p_imgs):
        if os.path.exists(os.path.join(img_dir1, img)):
            img_X1[i] = misc.imread(os.path.join(img_dir1, img))
        else:
            img_X1[i] = misc.imread(os.path.join(img_dir2, img))
    label[0:n1, 1] = 1

    n_imgs = random.sample(n_imgs, n0)
    for i, img in enumerate(n_imgs):
        img_X0[i] = misc.imread(os.path.join(img_dir2, img))
    label[n1:(n1 + n0), 0] = 1

    j = range(n1 + n0)
    random.shuffle(j)
    X = np.concatenate((img_X1, img_X0))
    return X[j], label[j], p_imgs, n_imgs


def active_sampling(m0, train_imgs, ms_p_imgs, ms_n_imgs, act_n, p_imgs, n_imgs):
    ms_p_n = 20 * act_n
    ms_p_imgs = random.sample(ms_p_imgs, ms_p_n)
    ms_X = np.zeros((ms_p_n, 256, 256, 3))
    ms_img = []
    img_dir1 = '../data/image_project_922/'
    i = 0
    for [task_x, task_y] in ms_p_imgs:
        img = '%s-%s.jpeg' % (task_x, task_y)
        img_f = os.path.join(img_dir1, img)
        if os.path.exists(img_f) and img in train_imgs and img not in p_imgs:
            ms_X[i] = misc.imread(img_f)
            ms_img.append(img)
            i += 1
    print '%d MapSwipe positive image candidates for prediction' % i

    X = ms_X[0:i]
    ms_img = ms_img[0:i]
    m0.set_prediction_input(X)
    scores, _ = m0.predict()

    img_X = np.zeros((act_n, 256, 256, 3))
    j = 0
    print 'MapSwipe positive images: score predicted by M0'
    for k, score in enumerate(scores):
        if 0.5 > score:
            print '%s: %f' % (ms_img[k], score)
            img_X[j] = X[k]
            j += 1
        if j >= act_n:
            break
    real_act_n = j
    print '%d actively sampled positive images' % real_act_n
    img_X_ap = img_X[0:real_act_n]
    label_ap = np.zeros((real_act_n, 2))
    label_ap[:, 1] = 1

    img_X = np.zeros((real_act_n, 256, 256, 3))
    j = 0
    img_dir2 = '../data/image_project_922_negative/'
    for [task_x, task_y] in ms_n_imgs:
        img = '%s-%s.jpeg' % (task_x, task_y)
        img_f = os.path.join(img_dir2, img)
        if img in train_imgs and img not in n_imgs:
            img_X[j] = misc.imread(img_f)
            j += 1
            if j >= real_act_n:
                break
    real_act_n2 = j
    print '%d actively sampled negative images' % real_act_n2
    img_X_an = img_X[0:real_act_n2]
    label_an = np.zeros((real_act_n2, 2))
    label_an[:, 0] = 1

    return np.concatenate((img_X_ap, img_X_an)), np.concatenate((label_ap, label_an))


if __name__ == '__main__':
    evaluate_only, external_test, tr_n1, tr_n0, tr_b, tr_e, tr_t, cv_i, te_n, nn, act_n = Parameters.deal_args(
        sys.argv[1:])
    cv_n = 4

    print '--------------- Read Samples ---------------'
    start_time = time.time()
    client = MapSwipe.MSClient()
    ms_p_imgs = client.read_p_images()
    ms_n_imgs = client.read_n_images()
    train_imgs, test_imgs = client.imgs_cross_validation(cv_i, cv_n)
    img_X, Y, p_imgs, n_imgs = read_train_sample(tr_n1, tr_n0, train_imgs, ms_n_imgs)
    print "time spent for reading samples: %s seconds\n" % (time.time() - start_time)

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
        img_Xa, Ya = active_sampling(m, train_imgs, ms_p_imgs, ms_n_imgs, act_n, p_imgs, n_imgs)
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

    del img_X, Y, train_imgs, p_imgs, n_imgs
    gc.collect()

    print '--------------- Ma: Evaluation on MapSwipe Samples ---------------'
    img_X2, Y2 = read_test_sample(te_n, test_imgs, ms_p_imgs, ms_n_imgs)
    m.set_evaluation_input(img_X2, Y2)
    m.evaluate()
    del img_X2, Y2
    gc.collect()

    if external_test:
        print '--------------- Ma: Evaluation on Expert  Labeled Samples ---------------'
        img_X3, Y3, _ = FileIO.read_external_test_sample()
        m.set_evaluation_input(img_X3, Y3)
        m.evaluate(True)
        del img_X3, Y3
        gc.collect()
