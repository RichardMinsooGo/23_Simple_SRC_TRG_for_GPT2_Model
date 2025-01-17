import os
import re
import time
import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
import unicodedata

import tensorflow_datasets as tfds

from tqdm import tqdm, tqdm_notebook, trange

from tensorflow.keras.layers import Dense, Input
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.models import Model

print("Tensorflow version {}".format(tf.__version__))
tf.random.set_seed(1234)
AUTO = tf.data.experimental.AUTOTUNE

ENCODER_LEN = 41
DECODER_LEN = ENCODER_LEN
BATCH_SIZE  = 128
BUFFER_SIZE = 20000

N_EPOCHS = 20

import urllib3
import zipfile
import shutil
import pandas as pd

pd.set_option('display.max_colwidth', None)

http = urllib3.PoolManager()
url = 'http://www.cs.cornell.edu/~cristian/data/cornell_movie_dialogs_corpus.zip'
filename = 'cornell_movie_dialogs_corpus.zip'
path = os.getcwd()
zipfilename = os.path.join(path, filename)
with http.request('GET', url, preload_content=False) as r, open(zipfilename, 'wb') as out_file:       
    shutil.copyfileobj(r, out_file)

with zipfile.ZipFile(zipfilename, 'r') as zip_ref:
    zip_ref.extractall(path)

# ! unzip cornell_movie_dialogs_corpus.zip
path_to_movie_lines = '/content/cornell movie-dialogs corpus/movie_lines.txt'
path_to_movie_conversations = '/content/cornell movie-dialogs corpus/movie_conversations.txt'

# Option 1
def preprocess_eng(sentence):
    sentence = sentence.lower().strip()
    # creating a space between a word and the punctuation following it
    # eg: "he is a boy." => "he is a boy ."
    sentence = re.sub(r"([?.!,])", r" \1 ", sentence)
    sentence = re.sub(r'[" "]+', " ", sentence)
    # removing contractions
    sentence = re.sub(r"i'm", "i am", sentence)
    sentence = re.sub(r"he's", "he is", sentence)
    sentence = re.sub(r"she's", "she is", sentence)
    sentence = re.sub(r"it's", "it is", sentence)
    sentence = re.sub(r"that's", "that is", sentence)
    sentence = re.sub(r"what's", "that is", sentence)
    sentence = re.sub(r"where's", "where is", sentence)
    sentence = re.sub(r"how's", "how is", sentence)
    sentence = re.sub(r"\'ll", " will", sentence)
    sentence = re.sub(r"\'ve", " have", sentence)
    sentence = re.sub(r"\'re", " are", sentence)
    sentence = re.sub(r"\'d", " would", sentence)
    sentence = re.sub(r"\'re", " are", sentence)
    sentence = re.sub(r"won't", "will not", sentence)
    sentence = re.sub(r"can't", "cannot", sentence)
    sentence = re.sub(r"n't", " not", sentence)
    sentence = re.sub(r"n'", "ng", sentence)
    sentence = re.sub(r"'bout", "about", sentence)
    # replacing everything with space except (a-z, A-Z, ".", "?", "!", ",")
    sentence = re.sub(r"[^a-zA-Z?.!,]+", " ", sentence)
    sentence = sentence.strip()
    return sentence

def load_preprocessed_data():
    # dictionary of line id to text
    id2line = {}
    with open(path_to_movie_lines, errors='ignore') as file:
        lines = file.readlines()
    for line in lines:
        parts = line.replace('\n', '').split(' +++$+++ ')
        id2line[parts[0]] = parts[4]

    processed_src, processed_trg = [], []
    with open(path_to_movie_conversations, 'r') as file:
        lines = file.readlines()
    for line in lines:
        parts = line.replace('\n', '').split(' +++$+++ ')
        # get conversation in a list of line ID
        conversation = [line[1:-1] for line in parts[3][1:-1].split(', ')]
        for i in range(len(conversation) - 1):
            processed_src.append(preprocess_eng(id2line[conversation[i]]))
            processed_trg.append(preprocess_eng(id2line[conversation[i + 1]]))

    return processed_src, processed_trg

# 인코딩 테스트
en_sent = u"Have you had dinner?"
print(preprocess_eng(en_sent))

processed_src, processed_trg = load_preprocessed_data()

print('Sample question: {}'.format(processed_src[20]))
print('Sample answer  : {}'.format(processed_trg[20]))

df1 = pd.DataFrame(processed_src)
df2 = pd.DataFrame(processed_trg)

df1.rename(columns={0: "SRC"}, errors="raise", inplace=True)
df2.rename(columns={0: "TRG"}, errors="raise", inplace=True)
train_df = pd.concat([df1, df2], axis=1)

train_df["src_len"] = ""
train_df["trg_len"] = ""
train_df.head()

for idx in range(len(train_df['SRC'])):
    # initialize string
    text_eng = str(train_df.iloc[idx]['SRC'])

    # default separator: space
    result_eng = len(text_eng.split())
    train_df.at[idx, 'src_len'] = int(result_eng)

    text_fra = str(train_df.iloc[idx]['TRG'])
    # default separator: space
    result_fra = len(text_fra.split())
    train_df.at[idx, 'trg_len'] = int(result_fra)

print('Translation Pair :',len(train_df)) # 리뷰 개수 출력

train_df = train_df.drop_duplicates(subset = ["SRC"])
print('Translation Pair :',len(train_df)) # 리뷰 개수 출력

train_df = train_df.drop_duplicates(subset = ["TRG"])
print('Translation Pair :',len(train_df)) # 리뷰 개수 출력

# 그 결과를 새로운 변수에 할당합니다.
is_within_len = (4 < train_df['src_len']) & (train_df['src_len'] <= 20) & (4 < train_df['trg_len']) & (train_df['trg_len'] <=20)
# 조건를 충족하는 데이터를 필터링하여 새로운 변수에 저장합니다.
train_df = train_df[is_within_len]

dataset_df_8096 = train_df.sample(n=1024*8, # number of items from axis to return.
          random_state=1234) # seed for random number generator for reproducibility

print('Translation Pair :',len(dataset_df_8096)) # 리뷰 개수 출력

raw_src = dataset_df_8096['SRC'].tolist()
raw_trg = dataset_df_8096['TRG'].tolist()

len(raw_src)

print(raw_src[:5])
print(raw_trg[:5])

print('Translation Pair :',len(raw_src)) # 리뷰 개수 출력


# 서브워드텍스트인코더를 사용하여 질문과 답변을 모두 포함한 단어 집합(Vocabulary) 생성
SRC_tokenizer = tfds.deprecated.text.SubwordTextEncoder.build_from_corpus(
    raw_src, target_vocab_size=2**13)

# 서브워드텍스트인코더를 사용하여 질문과 답변을 모두 포함한 단어 집합(Vocabulary) 생성
TRG_tokenizer = tfds.deprecated.text.SubwordTextEncoder.build_from_corpus(
    raw_trg, target_vocab_size=2**13)

# 시작 토큰과 종료 토큰에 대한 정수 부여.
START_TOKEN, END_TOKEN = [TRG_tokenizer.vocab_size], [TRG_tokenizer.vocab_size + 1]

# 시작 토큰과 종료 토큰을 고려하여 단어 집합의 크기를 + 2
n_enc_vocab = SRC_tokenizer.vocab_size
n_dec_vocab = TRG_tokenizer.vocab_size + 2

print('시작 토큰 번호           :',START_TOKEN)
print('종료 토큰 번호           :',END_TOKEN)
print('Encoder 단어 집합의 크기 :',n_enc_vocab)
print('Decoder 단어 집합의 크기 :',n_dec_vocab)

lines = [
  "It is winter and the weather is very cold.",
  "Will this Christmas be a white Christmas?",
  "Be careful not to catch a cold in winter and have a happy new year."
]
for line in lines:
    txt_2_ids = SRC_tokenizer.encode(line)
    ids_2_txt = SRC_tokenizer.decode(txt_2_ids)
    print("Input     :", line)
    print("txt_2_ids :", txt_2_ids)
    print("ids_2_txt :", ids_2_txt,"\n")

    
# 각 정수는 각 단어와 어떻게 mapping되는지 병렬로 출력
# 서브워드텍스트인코더는 의미있는 단위의 서브워드로 토크나이징한다. 띄어쓰기 단위 X 형태소 분석 단위 X
for ts in txt_2_ids:
    print ('{} ----> {}'.format(ts, SRC_tokenizer.decode([ts])))

# 토큰화 / 정수 인코딩 / 시작 토큰과 종료 토큰 추가 / 패딩
tokenized_inputs, tokenized_outputs = [], []

for (sentence1, sentence2) in zip(raw_src, raw_trg):
    sentence1 = SRC_tokenizer.encode(sentence1)
    sentence2 = START_TOKEN + TRG_tokenizer.encode(sentence2) + END_TOKEN

    tokenized_inputs.append(sentence1)
    tokenized_outputs.append(sentence2)

# 패딩
tkn_sources = tf.keras.preprocessing.sequence.pad_sequences(tokenized_inputs,  maxlen=ENCODER_LEN, padding='post', truncating='post')
tkn_targets = tf.keras.preprocessing.sequence.pad_sequences(tokenized_outputs, maxlen=DECODER_LEN, padding='post', truncating='post')

tensors_src   = tf.cast(tkn_sources, dtype=tf.int64)
tensors_trg   = tf.cast(tkn_targets, dtype=tf.int64)

print('질문 데이터의 크기(shape) :', tensors_src.shape)
print('답변 데이터의 크기(shape) :', tensors_trg.shape)

# 0번째 샘플을 임의로 출력
print(tkn_sources[0])
print(tkn_targets[0])

# Hyper-parameters
n_layers  = 2     # 6
hid_dim   = 256
pf_dim    = 1024
n_heads   = 8
dropout   = 0.3

dataset = tf.data.Dataset.from_tensor_slices((tensors_src, tensors_trg))

dataset = dataset.cache()
dataset = dataset.shuffle(BUFFER_SIZE)
dataset = dataset.batch(BATCH_SIZE)
dataset = dataset.prefetch(tf.data.experimental.AUTOTUNE)

""" attention pad mask """
def create_padding_mask(seq):
    seq = tf.cast(tf.math.equal(seq, 0), tf.float32)
    # (batch_size, 1, 1, key의 문장 길이)
    return seq[:, tf.newaxis, tf.newaxis, :]

""" attention decoder mask """
def create_look_ahead_mask(size):
    mask = 1 - tf.linalg.band_part(tf.ones((size, size)), -1, 0)
    return mask

import math

""" scale dot product attention """
class ScaledDotProductAttention(tf.keras.layers.Layer):

    def __init__(self):
        super().__init__()
        self.dropout = tf.keras.layers.Dropout(dropout)
        self.num_buckets = 32
        self.relative_attention_bias = tf.keras.layers.Embedding(
            self.num_buckets, n_heads,
            name="relative_attention_bias",
        )
        
    # def call(self, query, key, value, mask):
    def call(self, query, key, value, mask, bidirectional=True):

        tensor_shape_tuple = query.get_shape()
        tensor_shape_list = tensor_shape_tuple.as_list()
        qlen = int(tensor_shape_list[-2])
        
        tensor_shape_tuple = key.get_shape()
        tensor_shape_list = tensor_shape_tuple.as_list()    
        klen = int(tensor_shape_list[-2])

        matmul_qk = tf.matmul(query, key, transpose_b=True)  # (..., seq_len_q, seq_len_k)

        # scale matmul_qk
        dk = tf.cast(tf.shape(key)[-1], tf.float32)
        scaled_attention_logits = matmul_qk / tf.math.sqrt(dk)
        
        position_bias = self.compute_bias(qlen, klen, bidirectional=bidirectional)
        
        # print("position_bias :\n", position_bias)
        # import sys
        # sys.exit()
        
        scaled_attention_logits += position_bias
        

        # add the mask to the scaled tensor.
        if mask is not None:
            scaled_attention_logits += (mask * -1e9)

        # softmax is normalized on the last axis (seq_len_k) so that the scores
        # add up to 1.
        attention_weights = tf.nn.softmax(scaled_attention_logits, axis=-1)  # (..., seq_len_q, seq_len_k)

        output = tf.matmul(attention_weights, value)  # (..., seq_len_q, depth_v)

        return output, attention_weights
    
    """Compute binned relative position bias"""

    def compute_bias(self, qlen, klen, bidirectional=True):
        """ Compute binned relative position bias """
        context_position = tf.range(qlen)[:, None]
        memory_position = tf.range(klen)[None, :]
        relative_position = memory_position - context_position  # shape (qlen, klen)
        rp_bucket = self._relative_position_bucket(
            relative_position,
            bidirectional = bidirectional,
            num_buckets=self.num_buckets,
        )
        # print("@@@@@ rp_bucket        :\n", rp_bucket)        
        # print("@@@@@ self.num_buckets :\n", self.num_buckets)
        # print("@@@@@ self.relative_attention_bias :\n", self.relative_attention_bias)

        values = self.relative_attention_bias(rp_bucket)  # shape (qlen, klen, num_heads)
        values = tf.expand_dims(tf.transpose(values, [2, 0, 1]), axis=0)  # shape (1, num_heads, qlen, klen)
        return values

    def _relative_position_bucket(self, relative_position, num_buckets=32, bidirectional=True, max_distance=128):
        """
        Adapted from Mesh Tensorflow:
        https://github.com/tensorflow/mesh/blob/0cb87fe07da627bf0b7e60475d59f95ed6b5be3d/mesh_tensorflow/transformer/transformer_layers.py#L593

        Translate relative position to a bucket number for relative attention. The relative position is defined as
        memory_position - query_position, i.e. the distance in tokens from the attending position to the attended-to
        position. If bidirectional=False, then positive relative positions are invalid. We use smaller buckets for
        small absolute relative_position and larger buckets for larger absolute relative_positions. All relative
        positions >=max_distance map to the same bucket. All relative positions <=-max_distance map to the same bucket.
        This should allow for more graceful generalization to longer sequences than the model has been trained on

        Args:
            relative_position: an int32 Tensor
            bidirectional: a boolean - whether the attention is bidirectional
            num_buckets: an integer
            max_distance: an integer

        Returns:
            a Tensor with the same shape as relative_position, containing int32 values in the range [0, num_buckets)
        """
        relative_buckets = 0
        #        n = -relative_position
        if bidirectional:
            num_buckets //= 2
            relative_buckets += (
                tf.cast(tf.math.greater(relative_position, 0), dtype=relative_position.dtype) * num_buckets
            )
            relative_position = tf.math.abs(relative_position)
        else:
            relative_position = -tf.math.minimum(relative_position, 0)
        # now n is in the range [0, inf)
        max_exact = num_buckets // 2
        is_small = tf.math.less(relative_position, max_exact)
        relative_position_if_large = max_exact + tf.cast(
            tf.math.log(relative_position / max_exact)
            / math.log(max_distance / max_exact)
            * (num_buckets - max_exact),
            dtype=relative_position.dtype,
        )
        relative_position_if_large = tf.math.minimum(relative_position_if_large, num_buckets - 1)
        relative_buckets += tf.where(is_small, relative_position, relative_position_if_large)
        return relative_buckets

""" multi head attention """
class MultiHeadAttentionLayer(tf.keras.layers.Layer):
    
    def __init__(self, hid_dim, n_heads):
        super(MultiHeadAttentionLayer, self).__init__()
        self.n_heads = n_heads
        assert hid_dim % self.n_heads == 0
        self.hid_dim = hid_dim
        
        # hid_dim을 n_heads로 나눈 값.
        self.depth = int(hid_dim/self.n_heads)
        
        # WQ, WK, WV에 해당하는 밀집층 정의
        self.q_linear = tf.keras.layers.Dense(hid_dim)
        self.k_linear = tf.keras.layers.Dense(hid_dim)
        self.v_linear = tf.keras.layers.Dense(hid_dim)
        
        self.scaled_dot_attn = ScaledDotProductAttention()
        
        # WO에 해당하는 밀집층 정의
        self.out = tf.keras.layers.Dense(hid_dim)

    def split_heads(self, inputs, batch_size):
        """Split the last dimension into (n_heads, depth).
        Transpose the result such that the shape is (batch_size, n_heads, seq_len, depth)
        """
        inputs = tf.reshape(
            inputs, (batch_size, -1, self.n_heads, self.depth))
        return tf.transpose(inputs, perm=[0, 2, 1, 3])

    def call(self, value, key, query, mask, bidirectional = False):
        batch_size = tf.shape(query)[0]
        # 1. WQ, WK, WV에 해당하는 밀집층 지나기
        # q : (batch_size, query의 문장 길이, hid_dim)
        # k : (batch_size, key의 문장 길이, hid_dim)
        # v : (batch_size, value의 문장 길이, hid_dim)
        query = self.q_linear(query)
        key   = self.k_linear(key)
        value = self.v_linear(value)
        
        # 2. 헤드 나누기
        # q : (batch_size, n_heads, query의 문장 길이, hid_dim/n_heads)
        # k : (batch_size, n_heads, key의 문장 길이,   hid_dim/n_heads)
        # v : (batch_size, n_heads, value의 문장 길이, hid_dim/n_heads)
        query = self.split_heads(query, batch_size)
        key   = self.split_heads(key, batch_size)
        value = self.split_heads(value, batch_size)
        
        # 3. 스케일드 닷 프로덕트 어텐션. 앞서 구현한 함수 사용.
        # (batch_size, n_heads, query의 문장 길이, hid_dim/n_heads)
        # attention_weights.shape == (batch_size, n_heads, seq_len_q, seq_len_k)
        scaled_attention, attention_weights = self.scaled_dot_attn(
            query, key, value, mask, bidirectional = bidirectional)
        
        # (batch_size, query의 문장 길이, n_heads, hid_dim/n_heads)
        scaled_attention = tf.transpose(scaled_attention, perm=[0, 2, 1, 3])
        
        # 4. 헤드 연결(concatenate)하기
        # (batch_size, query의 문장 길이, hid_dim)
        concat_attention = tf.reshape(scaled_attention,
                                      (batch_size, -1, self.hid_dim))
        
        # 5. WO에 해당하는 밀집층 지나기
        # (batch_size, query의 문장 길이, hid_dim)
        outputs = self.out(concat_attention)

        return outputs, attention_weights

""" feed forward """
class PositionwiseFeedforwardLayer(tf.keras.layers.Layer):
    def __init__(self, hid_dim, pf_dim):
        super(PositionwiseFeedforwardLayer, self).__init__()
        self.linear_1 = tf.keras.layers.Dense(pf_dim, activation='relu')
        self.linear_2 = tf.keras.layers.Dense(hid_dim)

    def forward(self, attention):
        output = self.linear_1(attention)
        output = self.linear_2(output)
        return output

""" encoder layer """
class EncoderLayer(tf.keras.layers.Layer):
    def __init__(self, pf_dim, hid_dim, n_heads, dropout):
        super(EncoderLayer, self).__init__()
        
        self.attn = MultiHeadAttentionLayer(hid_dim, n_heads)
        self.ffn = PositionwiseFeedforwardLayer(hid_dim, pf_dim)
        
        self.layernorm1 = tf.keras.layers.LayerNormalization(epsilon=1e-6)
        self.layernorm2 = tf.keras.layers.LayerNormalization(epsilon=1e-6)
        
        self.dropout1 = tf.keras.layers.Dropout(dropout)
        self.dropout2 = tf.keras.layers.Dropout(dropout)

    def call(self, inputs, training, padding_mask):
        attention, _ = self.attn(inputs, inputs, inputs, padding_mask)  # (batch_size, input_seq_len, hid_dim)
        attention   = self.dropout1(attention, training=training)
        attention   = self.layernorm1(inputs + attention)  # (batch_size, input_seq_len, hid_dim)
        
        ffn_outputs = self.ffn(attention)  # (batch_size, input_seq_len, hid_dim)
        ffn_outputs = self.dropout2(ffn_outputs, training=training)
        ffn_outputs = self.layernorm2(attention + ffn_outputs)  # (batch_size, input_seq_len, hid_dim)

        return ffn_outputs

""" encoder """
class Encoder(tf.keras.layers.Layer):
    def __init__(self, n_enc_vocab, n_layers, pf_dim, hid_dim, n_heads,
                 maximum_position_encoding, dropout):
        super(Encoder, self).__init__()

        self.hid_dim  = hid_dim
        self.n_layers = n_layers

        self.embedding = tf.keras.layers.Embedding(n_enc_vocab, hid_dim)
        self.enc_layers = [EncoderLayer(pf_dim, hid_dim, n_heads, dropout)
                           for _ in range(n_layers)]

        self.dropout1 = tf.keras.layers.Dropout(dropout)

    def call(self, x, training, padding_mask):
        seq_len = tf.shape(x)[1]

        # adding embedding and position encoding.
        emb = self.embedding(x)  # (batch_size, input_seq_len, hid_dim)

        output = self.dropout1(emb, training=training)

        for i in range(self.n_layers):
            output = self.enc_layers[i](output, training, padding_mask)

        return output  # (batch_size, input_seq_len, hid_dim)
    
""" decoder layer """
class DecoderLayer(tf.keras.layers.Layer):
    def __init__(self, pf_dim, hid_dim, n_heads, dropout):
        super(DecoderLayer, self).__init__()

        self.attn   = MultiHeadAttentionLayer(hid_dim, n_heads)
        self.attn_2 = MultiHeadAttentionLayer(hid_dim, n_heads)

        self.ffn = PositionwiseFeedforwardLayer(hid_dim, pf_dim)

        self.layernorm1 = tf.keras.layers.LayerNormalization(epsilon=1e-6)
        self.layernorm2 = tf.keras.layers.LayerNormalization(epsilon=1e-6)
        self.layernorm3 = tf.keras.layers.LayerNormalization(epsilon=1e-6)

        self.dropout1 = tf.keras.layers.Dropout(dropout)
        self.dropout2 = tf.keras.layers.Dropout(dropout)
        self.dropout3 = tf.keras.layers.Dropout(dropout)

    def call(self, inputs, enc_output, training,
             look_ahead_mask, padding_mask):
        # enc_output.shape == (batch_size, input_seq_len, hid_dim)

        attention1, attn_weights_block1 = self.attn(
            inputs, inputs, inputs, look_ahead_mask)  # (batch_size, target_seq_len, hid_dim)
        attention1 = self.dropout1(attention1, training=training)
        attention1 = self.layernorm1(inputs + attention1)

        attention2, attn_weights_block2 = self.attn_2(
            enc_output, enc_output, attention1, padding_mask)  # (batch_size, target_seq_len, hid_dim)
        attention2 = self.dropout2(attention2, training=training)
        attention2 = self.layernorm2(attention1 + attention2)  # (batch_size, target_seq_len, hid_dim)

        ffn_outputs = self.ffn(attention2)  # (batch_size, target_seq_len, hid_dim)
        ffn_outputs = self.dropout3(ffn_outputs, training=training)
        ffn_outputs = self.layernorm3(attention2 + ffn_outputs)  # (batch_size, target_seq_len, hid_dim)

        return ffn_outputs, attn_weights_block1, attn_weights_block2

""" decoder """
class Decoder(tf.keras.layers.Layer):
    def __init__(self, n_dec_vocab, n_layers, pf_dim, hid_dim, n_heads, 
                 maximum_position_encoding, dropout):
        super(Decoder, self).__init__()

        self.hid_dim = hid_dim
        self.n_layers = n_layers

        self.embedding = tf.keras.layers.Embedding(n_dec_vocab, hid_dim)
        self.dec_layers = [DecoderLayer(pf_dim, hid_dim, n_heads, dropout)
                           for _ in range(n_layers)]
        self.dropout = tf.keras.layers.Dropout(dropout)

    def call(self, dec_input, enc_output, training,
             look_ahead_mask, padding_mask):

        seq_len = tf.shape(dec_input)[1]
        attention_weights = {}

        emb = self.embedding(dec_input)

        output = self.dropout(emb, training=training)

        for i in range(self.n_layers):
            output, block1, block2 = self.dec_layers[i](output, enc_output, training,
                                                   look_ahead_mask, padding_mask)

            attention_weights['decoder_layer{}_block1'.format(i+1)] = block1
            attention_weights['decoder_layer{}_block2'.format(i+1)] = block2
    
        return output, attention_weights
    
def create_masks(inp, tar):
    enc_padding_mask = create_padding_mask(inp)
    dec_padding_mask = create_padding_mask(inp)

    look_ahead_mask = create_look_ahead_mask(tf.shape(tar)[1])
    dec_target_padding_mask = create_padding_mask(tar)
    look_ahead_mask = tf.maximum(dec_target_padding_mask, look_ahead_mask)
  
    return enc_padding_mask, look_ahead_mask, dec_padding_mask

# Model Define for Training
""" transformer """
class Transformer(tf.keras.Model):

    def __init__(self, n_enc_vocab, n_dec_vocab,
                 n_layers, pf_dim, hid_dim, n_heads,
                 pe_input, pe_target, dropout):
        super(Transformer, self).__init__()
        self.encoder = Encoder(n_enc_vocab,
                               n_layers, pf_dim, hid_dim, n_heads,
                               pe_input, dropout)

        self.decoder = Decoder(n_dec_vocab,
                               n_layers, pf_dim, hid_dim, n_heads,
                               pe_target, dropout)

        self.fin_output = tf.keras.layers.Dense(n_dec_vocab)
    
    def call(self, inp, tar, training, enc_padding_mask, look_ahead_mask, dec_padding_mask):
        enc_output = self.encoder(inp, training, enc_padding_mask)

        dec_output, attention_weights = self.decoder(
            tar, enc_output, training, look_ahead_mask, dec_padding_mask)

        final_output = self.fin_output(dec_output)

        return final_output, attention_weights

loss_object = tf.keras.losses.SparseCategoricalCrossentropy(
    from_logits=True, reduction='none')

def loss_function(real, pred):
    mask = tf.math.logical_not(tf.math.equal(real, 0))
    loss_ = loss_object(real, pred)

    mask = tf.cast(mask, dtype=loss_.dtype)
    loss_ *= mask

    return tf.reduce_sum(loss_)/tf.reduce_sum(mask)

class CustomSchedule(tf.keras.optimizers.schedules.LearningRateSchedule):
    def __init__(self, hid_dim, warmup_steps=4000):
        super(CustomSchedule, self).__init__()
        self.hid_dim = hid_dim
        self.hid_dim = tf.cast(self.hid_dim, tf.float32)
        self.warmup_steps = warmup_steps

    def __call__(self, step):
        arg1 = tf.math.rsqrt(step)
        arg2 = step * (self.warmup_steps ** -1.5)

        return tf.math.rsqrt(self.hid_dim) * tf.math.minimum(arg1, arg2)

learning_rate = CustomSchedule(hid_dim)

optimizer = tf.keras.optimizers.Adam(learning_rate, beta_1=0.9, beta_2=0.98,
                                     epsilon=1e-9)

temp_learning_rate_schedule = CustomSchedule(hid_dim)

plt.plot(temp_learning_rate_schedule(tf.range(40000, dtype=tf.float32)))
plt.ylabel("Learning Rate")
plt.xlabel("Train Step")

def accuracy_function(real, pred):
    accuracies = tf.equal(real, tf.argmax(pred, axis=2))
    mask = tf.math.logical_not(tf.math.equal(real, 0))
    accuracies = tf.math.logical_and(mask, accuracies)
    accuracies = tf.cast(accuracies, dtype=tf.float32)
    mask = tf.cast(mask, dtype=tf.float32)
    return tf.reduce_sum(accuracies)/tf.reduce_sum(mask)

train_loss = tf.keras.metrics.Mean(name='train_loss')
train_accuracy = tf.keras.metrics.Mean(name='train_accuracy')

"""## Training and checkpointing"""

model = Transformer(
    n_enc_vocab = n_enc_vocab,
    n_dec_vocab = n_dec_vocab,
    n_layers  = n_layers,
    pf_dim      = pf_dim,
    hid_dim     = hid_dim,
    n_heads     = n_heads,
    pe_input    = 512,
    pe_target   = 512,
    dropout     = dropout)

# tf.keras.utils.plot_model(
#     model, to_file='transformer.png', show_shapes=True)

checkpoint_path = "./checkpoints"

ckpt = tf.train.Checkpoint(model=model, optimizer=optimizer)

ckpt_manager = tf.train.CheckpointManager(ckpt, checkpoint_path, max_to_keep=5)

# if a checkpoint exists, restore the latest checkpoint.
if ckpt_manager.latest_checkpoint:
    ckpt.restore(ckpt_manager.latest_checkpoint)
    print('Latest checkpoint restored!!')

@tf.function
def train_step(inp, tar):
    tar_inp = tar[:, :-1]
    tar_real = tar[:, 1:]

    enc_padding_mask, combined_mask, dec_padding_mask = create_masks(inp, tar_inp)

    with tf.GradientTape() as tape:
        predictions, _ = model(inp, tar_inp, 
            True, 
            enc_padding_mask, 
            combined_mask, 
            dec_padding_mask
        )
        loss = loss_function(tar_real, predictions)

    gradients = tape.gradient(loss, model.trainable_variables)
    optimizer.apply_gradients(zip(gradients, model.trainable_variables))

    train_loss(loss)
    train_accuracy(accuracy_function(tar_real, predictions))

for epoch in range(N_EPOCHS):
    train_loss.reset_states()
    
    with tqdm_notebook(total=len(dataset), desc=f"Train {epoch+1}") as pbar:
        for (batch, (inp, tar)) in enumerate(dataset):
            train_step(inp, tar)
    
            pbar.update(1)
            pbar.set_postfix_str(f"Loss {train_loss.result():.4f} Accuracy {train_accuracy.result():.4f}")
            
    # print(f'Epoch {epoch + 1} Loss {train_loss.result():.4f} Accuracy {train_accuracy.result():.4f}')
    
ckpt_save_path = ckpt_manager.save()
print ('Saving checkpoint for epoch {} at {}'.format(epoch+1, ckpt_save_path))

def evaluate(text):
    text = preprocess_sentence(text)

    encoder_input = tf.expand_dims(SRC_tokenizer.encode(text), axis=0)

    output = tf.expand_dims(START_TOKEN, 0)

    # 디코더의 예측 시작
    for i in range(DECODER_LEN):
        enc_padding_mask, combined_mask, dec_padding_mask = create_masks(encoder_input, output)

        predictions, attention_weights = model(
            encoder_input, 
            output,
            False,
            enc_padding_mask,
            combined_mask,
            dec_padding_mask
        )


        # 현재(마지막) 시점의 예측 단어를 받아온다.
        predictions = predictions[:, -1:, :]
        predicted_id = tf.cast(tf.argmax(predictions, axis=-1), tf.int32)

        # 만약 마지막 시점의 예측 단어가 종료 토큰이라면 예측을 중단
        if tf.equal(predicted_id, END_TOKEN[0]):
            break

        # 마지막 시점의 예측 단어를 출력에 연결한다.
        # 이는 for문을 통해서 디코더의 입력으로 사용될 예정이다.
        output = tf.concat([output, predicted_id], axis=-1)

    return tf.squeeze(output, axis=0)

def predict(text):
    prediction = evaluate(text)

    predicted_sentence = TRG_tokenizer.decode(
        [i for i in prediction if i < TRG_tokenizer.vocab_size])
    
    return predicted_sentence

def preprocess_sentence(sentence):
    sentence = re.sub(r"([?.!,])", r" \1 ", sentence)
    sentence = sentence.strip()
    return sentence

for idx in (11, 21, 31, 41, 51):
    print("Input        :", raw_src[idx])
    print("Prediction   :", predict(raw_src[idx]))
    print("Ground Truth :", raw_trg[idx],"\n")
    