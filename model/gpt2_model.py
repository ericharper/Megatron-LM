# coding=utf-8
# Copyright (c) 2019, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""GPT-2 model."""

import torch

from megatron.module import MegatronModule

from .language_model import parallel_lm_logits
from .language_model import get_language_model
from .utils import init_method_normal
from .utils import scaled_init_method_normal


def gpt2_attention_mask_func(attention_scores, ltor_mask):
    attention_scores = torch.mul(attention_scores, ltor_mask) - \
                       10000.0 * (1.0 - ltor_mask)
    return attention_scores


class GPT2Model(MegatronModule):
    """GPT-2 Language model."""

    def __init__(self,
                 num_layers,
                 vocab_size,
                 hidden_size,
                 num_attention_heads,
                 embedding_dropout_prob,
                 attention_dropout_prob,
                 output_dropout_prob,
                 max_sequence_length,
                 checkpoint_activations,
                 checkpoint_num_layers=1,
                 layernorm_epsilon=1.0e-5,
                 init_method_std=0.02,
                 num_tokentypes=0,
                 parallel_output=True):

        super(GPT2Model, self).__init__()

        self.parallel_output = parallel_output

        self.language_model, self._language_model_key = get_language_model(
            num_layers=num_layers,
            vocab_size=vocab_size,
            hidden_size=hidden_size,
            num_attention_heads=num_attention_heads,
            embedding_dropout_prob=embedding_dropout_prob,
            attention_dropout_prob=attention_dropout_prob,
            output_dropout_prob=output_dropout_prob,
            max_sequence_length=max_sequence_length,
            num_tokentypes=num_tokentypes,
            add_pooler=False,
            attention_mask_func=gpt2_attention_mask_func,
            checkpoint_activations=checkpoint_activations,
            checkpoint_num_layers=checkpoint_num_layers,
            layernorm_epsilon=layernorm_epsilon,
            init_method=init_method_normal(init_method_std),
            scaled_init_method=scaled_init_method_normal(init_method_std,
                                                         num_layers),
            residual_connection_post_layernorm=False)


    def forward(self, input_ids, position_ids, attention_mask,
                tokentype_ids=None, layer_past=None, get_key_value=False):

        # Language model.
        lm_output = self.language_model(input_ids,
                                        position_ids,
                                        attention_mask,
                                        tokentype_ids=tokentype_ids,
                                        layer_past=layer_past,
                                        get_key_value=get_key_value)

        if get_key_value:
            lm_output, presents = lm_output

        # Output.
        output = parallel_lm_logits(
            lm_output,
            self.language_model.embedding.word_embeddings.weight,
            self.parallel_output)

        if get_key_value:
            output = [output, presents]

        return output


    def state_dict_for_save_checkpoint(self, destination=None, prefix='',
                                       keep_vars=False):

        state_dict_ = {}
        state_dict_[self._language_model_key] \
            = self.language_model.state_dict_for_save_checkpoint(
                destination, prefix, keep_vars)
        return state_dict_


    def load_state_dict(self, state_dict, strict=True):
        """Customized load."""

        if self._language_model_key in state_dict:
            state_dict = state_dict[self._language_model_key]
        self.language_model.load_state_dict(state_dict, strict=strict)
