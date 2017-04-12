import tensorflow as tf
import numpy as np
from math import ceil
import sys
import os


class RNN(object):
    """ RNN model """
    def __init__(self, config, word_vectors=[]):
        self.dim_proj = config['dim_proj']
        self.layers = config['layers']
        # self.batch_size = config['batch_size']
        self.batch_size = tf.placeholder(tf.int32, name="batch_size")
        self.n_words = config['n_words']
        self.learning_rate = config['learning_rate']
        self.num_classes = config['classes_num']
        self.word_vectors = word_vectors
        self.global_step = tf.Variable(0, name="global_step", trainable=False)
        # self.str_summary_type = tf.placeholder(
        #     tf.string, name="str_summary_type")
        self.input_keep_prob = tf.placeholder(
            tf.float32, name="keep_prob_inp")
        self.output_keep_prob = tf.placeholder(
            tf.float32, name="keep_prob_out")
        self.sentence_len = config['sentence_len']
        self.max_gradient_norm = config["clip_threshold"]
        self.x = tf.placeholder(tf.int32, [None, self.sentence_len], name="x")
        self.y = tf.placeholder(tf.float32, [None, self.num_classes], name="y")
        # self.seq_lengths = tf.placeholder(
        #     tf.int32, shape=[None], name="early_stop")
        # self.seq_lengths = [self.n_words] * config['batch_size']
        # self.seq_lengths = tf.placeholder(
        #     tf.int32, shape=[None], name="seq_length")

        self.dropout_prob = tf.placeholder(tf.float32, name="dropout_prob")

        # values vital when using minibatches on dev set
        # really ugly workaround
        self.metrics_weight = tf.placeholder(tf.float32, name="metrics_weight")
        self.fixed_acc_value = tf.placeholder(tf.float32, name="f_acc_value")
        self.fixed_loss_value = tf.placeholder(tf.float32, name="f_loss_value")
        # self.train_phase = tf.placeholder(tf.bool, name="train_flag")


        self.make_graph(config)
        self.summarize(config)

    def make_graph(self, config):
        """ Build RNN graph """

        with tf.name_scope("word_embeddings"):
            #     self.word_embeddings = []
            #     all_embeddings = []
            #     # counter = 0
            #     for index_ in range(self.word_vectors.shape[0]):
            #         if config['train_embeddings'][index_] is None:
            #             continue
            #         extracted_emb = tf.get_variable(
            #             "W0_" + str(index_), shape=[self.n_words, self.edim],
            #             trainable=config['train_embeddings'][index_],
            #             initializer=tf.constant_initializer(
            #                 np.array(self.word_vectors[index_]))
            #         )
            #         self.word_embeddings.append(extracted_emb)
            #         temp = tf.nn.embedding_lookup(
            #             extracted_emb, self.x)
            #         all_embeddings.append(temp)
            # self.embedded_chars = tf.stack(all_embeddings, axis=3)

            # print ("emb_char shape: {}".format(self.embedded_chars.shape))
            # self.w_embeddings = tf.get_variable(
            #     "W_embeddings",
            #     [self.n_words, self.dim_proj],
            #     initializer=tf.random_uniform_initializer(-1.0, 1.0)

            # )
            self.w_embeddings = tf.Variable(
                tf.truncated_normal([self.n_words, self.dim_proj],
                                    stddev=0.01),
                name="W_embeddings")
            index_ = 0
            self.w_embeddings = tf.get_variable(
                "W0_" + str(index_),
                shape=[self.n_words, self.dim_proj],
                trainable=config['train_embeddings'][index_],
                initializer=tf.constant_initializer(
                    np.array(self.word_vectors[index_]))
            )

            embedded_tokens = tf.nn.embedding_lookup(
                self.w_embeddings, self.x)
            print("emb_tokens {} rnn_input  ".format(embedded_tokens.shape))
            # embedded_tokens_drop = tf.nn.dropout(embedded_tokens, self.dropout_keep_prob_embedding)
        # split sentences in word steps of size batch_size
        rnn_input = [embedded_tokens[:, i, :] for i in range(
            self.sentence_len)]

        # input_shape = [self.batch_size, self.sentence_len, self.dim_proj]
        # rnn_input = tf.Variable(tf.float32, input_shape)
        # assign_op = tf.assign(embedded_tokens, rnn_input, )

        # rnn_input = embedded_tokens
        # self.test = rnn_input[0]
        # rnn_input_back = [embedded_tokens[:, i, :] for i in range(
        #     self.sentence_len - 1, -1, -1)]
        with tf.name_scope("calc_sequences_length"):
            '''
            calculate actual lenght of each sentence -- known bug
            if a sentence ends with unknown tokens they are not considered
            in size, if they are at start or in between they are
            considered though
            '''
            # doesn't work due to zero padding and <UNK> being both zero
            # self.seq_lengths = tf.reduce_sum(tf.sign(self.x), 1)
            mask = tf.sign(self.x)
            range_ = tf.range(
                start=1, limit=self.sentence_len + 1, dtype=tf.int32)
            mask = tf.multiply(mask, range_, name="mask")
            self.seq_lengths = tf.reduce_max(mask, axis=1)

        with tf.name_scope("rnn_cell"):
            if config['GRU']:  # use GRU cell
                self.rnn_cell = tf.contrib.rnn.DropoutWrapper(
                    tf.contrib.rnn.GRUCell(num_units=self.dim_proj),
                    input_keep_prob=self.input_keep_prob,
                    output_keep_prob=self.output_keep_prob
                )
                if config['attention']:
                    self.rnn_cell = tf.contrib.rnn.AttentionCellWrapper(
                        cell=self.rnn_cell, attn_length=40, state_is_tuple=True
                    )

                # rnn_cell = tf.contrib.rnn.GRUCell(num_units=self.dim_proj)
            else:  # use lstm cell instead
                self.rnn_cell = tf.contrib.rnn.DropoutWrapper(
                    tf.contrib.rnn.LSTMCell(num_units=self.dim_proj),
                    input_keep_prob=self.input_keep_prob,
                    output_keep_prob=self.output_keep_prob
                )
                if config['attention']:
                    self.rnn_cell = tf.contrib.rnn.AttentionCellWrapper(
                        cell=self.rnn_cell, attn_length=40, state_is_tuple=True
                    )


            # create sequential rnn from single cells
            rnn_cell_seq = tf.contrib.rnn.MultiRNNCell(
                [self.rnn_cell] * self.layers, state_is_tuple=True)

            initial_state = rnn_cell_seq.zero_state(
                self.batch_size, tf.float32)
            # Create a recurrent neural network

            if config['bidirectional']:
                # rnn_cell_bw = tf.contrib.rnn.DropoutWrapper(
                #     tf.contrib.rnn.LSTMCell(num_units=self.dim_proj),
                #     input_keep_prob=self.input_keep_prob,
                #     output_keep_prob=self.output_keep_prob
                # )
                # rnn_cell_seq_bw = tf.contrib.rnn.MultiRNNCell(
                #     [rnn_cell] * self.layers
                # )
                output, state_fw, state_bw = tf.contrib.rnn.static_bidirectional_rnn(
                    inputs=rnn_input,
                    cell_fw=rnn_cell_seq,
                    cell_bw=rnn_cell_seq,
                    initial_state_fw=initial_state,
                    initial_state_bw=initial_state,
                    sequence_length=self.seq_lengths
                )
                # self.state_ = state_fw[-1][0] + state_bw[-1][0]
                # self.output = output
                # self.state_ = state_bw[-1][0]
                self.state_ = output[-1]
                # self.state_ = tf.concat([state_fw[-1][0], state_bw[-1][0]], 1)
                # self.state_1 = state_fw[-1][0]
                # self.state_2 = state_bw[-1][0]
                # self.state_ = tf.concat([state_bw[-1][1], state_bw[-1][0]], 1)
                self.times = 2

            else:
                # self.lengths = tf.reduce_sum(
                #     tf.reduce_max(tf.sign(self.x), 2), 1)
                # self.lengths = tf.reduce_sum(tf.sign(self.x), 1)
                output, state = tf.contrib.rnn.static_rnn(
                    rnn_cell_seq, rnn_input,
                    initial_state=initial_state,
                    sequence_length=self.seq_lengths
                )
                # output, state = tf.nn.dynamic_rnn(
                #     cell=rnn_cell_seq,
                #     inputs=rnn_input,
                #     initial_state=initial_state,
                #     # sequence_length=self.seq_lengths
                # )
                self.state_ = output[-1]
                self.output = output

                
                # out_shape = [self.batch_size, self.sentence_len, -1]
                self.poolings = []
                for i in range(self.sentence_len):
                    pool_shape = [self.batch_size, 1, -1, 1]
                    pool_input = tf.reshape(
                        self.output[i], pool_shape
                    )
                    pool = tf.nn.avg_pool(
                        pool_input, strides=[1, 1, 1, 1],
                        ksize=[1, 1, self.dim_proj, 1],
                        padding='VALID', name="avg_pool_ouput"
                    )
                    pool = tf.reshape(
                        pool, [-1])
                    self.poolings.append(pool)
                self.stacked_outputs = tf.stack(self.poolings)
                self.state_ = tf.matrix_transpose(
                    self.stacked_outputs, name="stacked_avg_outputs")
                # self.state_ = output[-1]


                # self.stacked_outputs = tf.reshape(
                #     self.stacked_outputs, out_shape)

                # self.output_pool = 
                # self.state_ = output[-1]
                self.times = 1
                # self.state = state[-1][0] + state[-1][1]
                # self.state_ = tf.concat([state[-1][0], state[-1][1]], 1)

                # self.state_all = state

        if config["pooling"]:
            with tf.name_scope("avg_pooling"):
                self.h_pool = tf.reshape(
                    self.state_, [self.batch_size, -1, 1, 1])
                self.pool = tf.nn.avg_pool(
                    self.h_pool, strides=[1, 1, 1, 1],
                    # ksize=[1, self.sentence_len + 1, 1, 1],
                    ksize=[1, self.times * self.dim_proj, 1, 1],
                    padding='VALID', name="pool"
                )
            with tf.name_scope("softmax"):
                self.flat_pool = tf.reshape(self.pool, [-1, 1])
                shape = [1, self.num_classes]
                W = tf.Variable(
                    tf.truncated_normal(shape, stddev=0.01), name='W'
                )
                b = tf.Variable(tf.constant(
                    0.1, shape=[self.num_classes]),
                    name="b"
                )
                self.scores = tf.nn.xw_plus_b(self.flat_pool, W, b)

        else:
            with tf.name_scope("drop_out"):
                # use the cell memory state for information on sentence embedding
                self.l_drop = tf.nn.dropout(
                    self.state_, self.dropout_prob, name="drop_out")
                # self.l_drop = self.state_

            with tf.name_scope("fc_layer"):
                # shape = [tf.shape(self.state_)[1], self.num_classes]
                shape = [self.times * self.dim_proj, self.num_classes]
                shape = [self.sentence_len, self.num_classes]
                W = tf.Variable(
                    tf.truncated_normal(shape, stddev=0.01), name="W",
                )
                b = tf.Variable(tf.constant(
                    0.1, shape=[self.num_classes]),
                    trainable=True, name="b"
                )

                self.scores = tf.nn.xw_plus_b(self.l_drop, W, b)
                # self.scores = tf.nn.sigmoid(self.scores, name='sigmoid')

        # self.y = tf.nn.softmax(self.scores)
        with tf.name_scope("predict"):
            self.predictions = tf.argmax(self.scores, 1)
            self.true_predictions = tf.argmax(self.y, 1)
            self.probs = tf.nn.softmax(self.scores)
        with tf.name_scope("loss"):
            self.losses = tf.nn.softmax_cross_entropy_with_logits(
                logits=self.scores, labels=self.y, name="losses")
            # self.total_loss = tf.reduce_sum(self.losses)
            self.mean_loss = tf.reduce_mean(self.losses)
        with tf.name_scope("accuracy"):
            self.correct_predictions = tf.equal(
                self.predictions, tf.argmax(self.y, 1))
            self.accuracy = tf.reduce_mean(
                tf.cast(self.correct_predictions, "float"), name="accuracy")

        params = tf.trainable_variables()
        # if self.train_phase:
        with tf.name_scope("train"):
            optimizer = tf.train.AdamOptimizer(self.learning_rate)
        gradients = tf.gradients(self.losses, params)
        clipped_gradients, norm = tf.clip_by_global_norm(
            gradients, self.max_gradient_norm)

        # with tf.name_scope("grad_norms"):
        #     grad_summ = tf.scalar_summary("grad_norms", norm)

        self.update = optimizer.apply_gradients(
            zip(clipped_gradients, params), global_step=self.global_step)
        # self.mean_loss = tf.scalar_summary("{0}_loss".format(
        #     self.str_summary_type), self.mean_loss)
        # acc_summ = tf.scalar_summary("{0}_accuracy".format(
        #     self.str_summary_type), self.accuracy)
        # self.merged = tf.merge_summary([self.mean_loss, acc_summ])
    # self.saver = tf.train.Saver(tf.globa())

    def summarize(self, config):
        # out_dir = config['out_dir']
        # Summaries for loss and accuracy

        # if config['bidirectional']:
        #     weight = config
        #     loss_summary = tf.summary.scalar("loss", self.mean_loss)
        #     acc_summary = tf.summary.scalar("accuracy", self.accuracy)
        # else:
        self.mean_loss = self.metrics_weight * self.mean_loss + \
            self.fixed_loss_value
        self.accuracy = self.metrics_weight * self.accuracy + \
            self.fixed_acc_value
        loss_summary = tf.summary.scalar("loss", self.mean_loss)
        acc_summary = tf.summary.scalar("accuracy", self.accuracy)
        # Train Summaries
        self.summary_op = tf.summary.merge([loss_summary, acc_summary])
        # Dev summaries
        # self.dev_summary_op = tf.summary.merge([loss_summary, acc_summary])


class RNN_Attention(object):

    """ RNN model  using attention"""
    def __init__(self, config, word_vectors=[]):
        self.dim_proj = config['dim_proj']
        self.layers = config['layers']
        # self.batch_size = config['batch_size']
        self.batch_size = tf.placeholder(tf.int32, name="batch_size")
        self.n_words = config['n_words']
        self.learning_rate = config['learning_rate']
        self.num_classes = config['classes_num']
        self.word_vectors = word_vectors
        self.global_step = tf.Variable(0, name="global_step", trainable=False)
        # self.str_summary_type = tf.placeholder(
        #     tf.string, name="str_summary_type")
        self.input_keep_prob = tf.placeholder(
            tf.float32, name="keep_prob_inp")
        self.output_keep_prob = tf.placeholder(
            tf.float32, name="keep_prob_out")
        self.sentence_len = config['sentence_len']
        self.max_gradient_norm = config["clip_threshold"]
        self.x = tf.placeholder(tf.int32, [None, self.sentence_len], name="x")
        self.y = tf.placeholder(tf.float32, [None, self.num_classes], name="y")
        # self.seq_lengths = tf.placeholder(
        #     tf.int32, shape=[None], name="early_stop")
        # self.seq_lengths = [self.n_words] * config['batch_size']
        # self.seq_lengths = tf.placeholder(
        #     tf.int32, shape=[None], name="seq_length")

        self.dropout_prob = tf.placeholder(tf.float32, name="dropout_prob")

        # values vital when using minibatches on dev set
        # really ugly workaround
        self.metrics_weight = tf.placeholder(tf.float32, name="metrics_weight")
        self.fixed_acc_value = tf.placeholder(tf.float32, name="f_acc_value")
        self.fixed_loss_value = tf.placeholder(tf.float32, name="f_loss_value")
        # self.train_phase = tf.placeholder(tf.bool, name="train_flag")

        self.make_graph(config)
        # self.attention()
        self.train()
        self.summarize(config)

    def make_graph(self, config):
        """ declare RNN graph """

        with tf.name_scope("word_embeddings"):
            """
            initialize embeddings currently able to use only one type of
            embeddings
            """
            index_ = 0
            self.w_embeddings = tf.get_variable(
                "W0_" + str(index_),
                shape=[self.n_words, self.dim_proj],
                trainable=config['train_embeddings'][index_],
                initializer=tf.constant_initializer(
                    np.array(self.word_vectors[index_]))
            )
            embedded_tokens = tf.nn.embedding_lookup(
                self.w_embeddings, self.x)
            print("emb_tokens {} rnn_input  ".format(embedded_tokens.shape))

        # split sentences in word steps of size batch_size
        rnn_input = [embedded_tokens[:, i, :] for i in range(
            self.sentence_len)]

        with tf.name_scope("calc_sequences_length"):
            '''
            calculate actual lenght of each sentence -- known bug
            if a sentence ends with unknown tokens they are not considered
            in size, if they are at start or in between they are
            considered though
            '''
            # this doesn't work due to zero padding and <UNK> being both zero
            # self.seq_lengths = tf.reduce_sum(tf.sign(self.x), 1)
            mask = tf.sign(self.x)
            range_ = tf.range(
                start=1, limit=self.sentence_len + 1, dtype=tf.int32)
            mask = tf.multiply(mask, range_, name="mask")
            self.seq_lengths = tf.reduce_max(mask, axis=1)

        with tf.name_scope("rnn_cell"):
            if config['GRU']:  # use GRU cell
                self.rnn_cell = tf.contrib.rnn.DropoutWrapper(
                    tf.contrib.rnn.GRUCell(num_units=self.dim_proj),
                    input_keep_prob=self.input_keep_prob,
                    output_keep_prob=self.output_keep_prob
                )

        # create sequential rnn from single cells
        rnn_cell_seq = tf.contrib.rnn.MultiRNNCell(
            [self.rnn_cell] * self.layers, state_is_tuple=True)

        initial_state = rnn_cell_seq.zero_state(
            self.batch_size, tf.float32)

        if config['bidirectional']:
            self.dimensionality_mult = 2
            output, state_fw, state_bw = tf.contrib.rnn.static_bidirectional_rnn(
                inputs=rnn_input,
                cell_fw=rnn_cell_seq,
                cell_bw=rnn_cell_seq,
                initial_state_fw=initial_state,
                initial_state_bw=initial_state,
                sequence_length=self.seq_lengths
            )
            self.output = output

        else:
            self.dimensionality_mult = 1
            output, state = tf.contrib.rnn.static_rnn(
                rnn_cell_seq, rnn_input,
                initial_state=initial_state,
                sequence_length=self.seq_lengths
            )
            self.out_state = state
            self.output = output

        self.attention()

    def attention(self):
        # TODO attention as a module
        with tf.name_scope("attention_fc_layer"):
            # reshape out put to be [batches, seq_length, word_dimensionality]
            print ("output {} length {}".format(
                self.output[0].shape, len(self.output)))
            self.output = np.asarray(self.output)
            self.output = tf.stack(list(self.output))
            print (" out____ ", self.output.get_shape())

            # don;t work because bathc size is variable
            # try tf.slice(input_, begin, size, name=None)
            # self.attention_input = [
            #     self.output[:, i, :] for i in range(self.batch_size)]

            # self.attention_input = [tf.slice(
            #     self.output, [0, i, 0], [-1, i + 1, -1])
            #     for i in range(self.batch_size)]

            # change dimensions sequence
            self.attention_input = tf.transpose(
                self.output, perm=[1, 0, 2])

            shape = [self.dim_proj * self.dimensionality_mult, 1]
            W = tf.Variable(
                tf.truncated_normal(shape, stddev=0.01),
                name="W_attent_fc"
            )
            b = tf.Variable(
                tf.constant(0.1, shape=[self.sentence_len]),
                name="b"
            )
            print (" attention___ ", self.attention_input.get_shape())
            # reshape 3d tensor to be mjltiplied by the weights
            temp_shape_in = [
                self.batch_size * self.sentence_len, self.dim_proj * self.dimensionality_mult]
            # shape_out = [self.batch_size, self.sentence_len, 1]
            shape_out = [self.batch_size, self.sentence_len]
            self.unormalized_att_scores = tf.reshape(
                tf.matmul(tf.reshape(
                    self.attention_input, temp_shape_in), W), shape_out)
            # relu
            self.unormalized_att_scores = tf.nn.relu(
                tf.nn.bias_add(self.unormalized_att_scores, b), name="relu")
            # or tanh
            # self.unormalized_att_scores = tf.nn.tanh(
            #     tf.nn.bias_add(self.unormalized_att_scores, b), name="tanh")
            # or sigmoid
            # self.unormalized_att_scores = tf.nn.sigmoid(
            #     tf.nn.bias_add(self.unormalized_att_scores, b), name="sigmoid")
        with tf.name_scope("attention_softmax"):
            self.attention_scores = tf.nn.softmax(self.unormalized_att_scores)
            print ("attentio scores +++ ", self.attention_scores.shape)
            print ("att input +++", self.attention_input.shape)
        with tf.name_scope("sentence_representation"):
            # sentences = []

            # for i in range(self.batch_size):
            #     temp = tf.multiply(
            #         self.attention_input[i], self.attention_scores[i])
            #     sentences.append(temp)
            # self.sentence_repr = tf.stack(sentences)

            self.attention_scores_exp = tf.expand_dims(
                self.attention_scores, 2)
            print ("attention_scores_exp ++ ", self.attention_scores_exp.shape)


            self.sentence_repr = tf.multiply(
                self.attention_input, self.attention_scores_exp)
            print ("sentence repr ++ ", self.sentence_repr.shape)
            self.sentence_repr = tf.reduce_sum(self.sentence_repr, 1)
            print ("sentence repr reduced ++ ", self.sentence_repr.shape)
            # TODO wtite it better and more modular
            self.state_ = self.sentence_repr

        with tf.name_scope("fc_layer"):
            shape = [self.dim_proj * self.dimensionality_mult, self.num_classes]
            W = tf.Variable(
                tf.truncated_normal(shape, stddev=0.01),
                name="W_fc_layer")
            b = tf.Variable(tf.constant(
                0.1, shape=[self.num_classes]),
                name="b"
            )
            self.scores = tf.nn.xw_plus_b(self.sentence_repr, W, b)

    def train(self):
        """ calculate accuracies, train and predict """
        with tf.name_scope("predict"):
            self.predictions = tf.argmax(self.scores, 1)
            self.true_predictions = tf.argmax(self.y, 1)
            self.probs = tf.nn.softmax(self.scores)
        with tf.name_scope("loss"):
            self.losses = tf.nn.softmax_cross_entropy_with_logits(
                logits=self.scores, labels=self.y, name="losses")
            # self.total_loss = tf.reduce_sum(self.losses)
            self.mean_loss = tf.reduce_mean(self.losses)
        with tf.name_scope("accuracy"):
            self.correct_predictions = tf.equal(
                self.predictions, tf.argmax(self.y, 1))
            self.accuracy = tf.reduce_mean(
                tf.cast(self.correct_predictions, "float"), name="accuracy")

        params = tf.trainable_variables()
        # if self.train_phase:
        with tf.name_scope("train"):
            optimizer = tf.train.AdamOptimizer(self.learning_rate)
        gradients = tf.gradients(self.losses, params)
        clipped_gradients, norm = tf.clip_by_global_norm(
            gradients, self.max_gradient_norm)

        # with tf.name_scope("grad_norms"):
        #     grad_summ = tf.scalar_summary("grad_norms", norm)

        self.update = optimizer.apply_gradients(
            zip(clipped_gradients, params), global_step=self.global_step)


    def summarize(self, config):
        # out_dir = config['out_dir']
        # Summaries for loss and accuracy

        # if config['bidirectional']:
        #     weight = config
        #     loss_summary = tf.summary.scalar("loss", self.mean_loss)
        #     acc_summary = tf.summary.scalar("accuracy", self.accuracy)
        # else:
        self.mean_loss = self.metrics_weight * self.mean_loss + \
            self.fixed_loss_value
        self.accuracy = self.metrics_weight * self.accuracy + \
            self.fixed_acc_value
        loss_summary = tf.summary.scalar("loss", self.mean_loss)
        acc_summary = tf.summary.scalar("accuracy", self.accuracy)
        # Summaries
        self.summary_op = tf.summary.merge([loss_summary, acc_summary])
        # Dev summaries
        # self.dev_summary_op = tf.summary.merge([loss_summary, acc_summary])
