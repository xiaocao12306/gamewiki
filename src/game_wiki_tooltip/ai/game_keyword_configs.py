"""
游戏特定关键词配置
===================

为每个游戏定义特定的关键词权重，以优化BM25搜索效果
"""

from typing import Dict, Any

class GameKeywordConfig:
    """游戏关键词配置基类"""
    
    # 通用游戏术语（所有游戏共享）
    COMMON_GAMING_KEYWORDS = {
        # 通用战术术语
        'guide': 2.0,
        'strategy': 2.0,
        'tips': 2.0,
        'build': 2.5,
        'loadout': 2.5,
        'best': 2.0,
        'meta': 2.0,
        'tier': 2.0,
        'rank': 2.0,
        
        # 通用游戏概念
        'damage': 2.0,
        'health': 2.0,
        'stats': 1.5,
        'upgrade': 2.0,
        'level': 1.5,
        'skill': 2.0,
        'ability': 2.0,
        
        # 中文通用术语
        '攻略': 2.0,
        '策略': 2.0,
        '技巧': 2.0,
        '配装': 2.5,
        '最佳': 2.0,
        '推荐': 2.0,
        '等级': 1.5,
        '技能': 2.0,
    }
    
    @classmethod
    def get_config(cls, game_name: str) -> Dict[str, Any]:
        """获取特定游戏的配置"""
        configs = {
            'helldiver2': Helldivers2Config,
            'dst': DSTConfig,
            'eldenring': EldenRingConfig,
            'civilization6': Civilization6Config,
        }
        
        config_class = configs.get(game_name, cls)
        return {
            'enemy_keywords': getattr(config_class, 'ENEMY_KEYWORDS', {}),
            'tactical_keywords': getattr(config_class, 'TACTICAL_KEYWORDS', {}),
            'item_keywords': getattr(config_class, 'ITEM_KEYWORDS', {}),
            'special_keywords': getattr(config_class, 'SPECIAL_KEYWORDS', {}),
            'common_keywords': cls.COMMON_GAMING_KEYWORDS,
        }


class Helldivers2Config(GameKeywordConfig):
    """Helldivers 2 特定配置"""
    
    ENEMY_KEYWORDS = {
        # Terminid敌人
        'bile titan': 5.0,
        'biletitan': 5.0,
        '胆汁泰坦': 5.0,
        'charger': 4.0,
        '冲锋者': 4.0,
        'stalker': 3.5,
        '潜行者': 3.5,
        'brood commander': 3.5,
        '族群指挥官': 3.5,
        
        # Automaton敌人
        'hulk': 5.0,
        '巨人机甲': 5.0,
        'factory strider': 4.5,
        '工厂行者': 4.5,
        'devastator': 4.0,
        '毁灭者': 4.0,
        'tank': 4.0,
        '坦克': 4.0,
    }
    
    TACTICAL_KEYWORDS = {
        # 弱点相关
        'weak point': 4.0,
        'weakness': 4.0,
        'weak spot': 4.0,
        '弱点': 4.0,
        '要害': 3.5,
        
        # 战术相关
        'stratagem': 3.5,
        'reinforcement': 3.0,
        'orbital': 3.0,
        '轨道': 3.0,
        '增援': 3.0,
    }
    
    ITEM_KEYWORDS = {
        # 反坦克武器
        'anti-tank': 3.0,
        'railgun': 3.0,
        'recoilless rifle': 3.0,
        'quasar cannon': 3.0,
        '反坦克': 3.0,
        '轨道炮': 3.0,
        
        # 支援武器
        'autocannon': 2.5,
        'arc thrower': 2.5,
        'flamethrower': 2.5,
        '自动加农炮': 2.5,
        '电弧发射器': 2.5,
        '火焰喷射器': 2.5,
    }


class DSTConfig(GameKeywordConfig):
    """Don't Starve Together 特定配置"""
    
    ENEMY_KEYWORDS = {
        # Boss
        'deerclops': 4.0,
        'dragonfly': 4.0,
        'bee queen': 4.0,
        'ancient fuelweaver': 4.5,
        'klaus': 4.0,
        '独眼巨鹿': 4.0,
        '龙蝇': 4.0,
        '蜂后': 4.0,
        
        # 常见敌对生物
        'hound': 3.0,
        'spider': 2.5,
        'tallbird': 2.5,
        'merm': 2.5,
        '猎犬': 3.0,
        '蜘蛛': 2.5,
        '高鸟': 2.5,
    }
    
    TACTICAL_KEYWORDS = {
        # 生存相关
        'sanity': 4.0,
        'hunger': 4.0,
        'health': 4.0,
        'temperature': 3.5,
        'wetness': 3.5,
        '理智': 4.0,
        '饥饿': 4.0,
        '生命': 4.0,
        '温度': 3.5,
        '潮湿': 3.5,
        
        # 季节相关
        'winter': 3.5,
        'summer': 3.5,
        'autumn': 3.0,
        'spring': 3.0,
        '冬天': 3.5,
        '夏天': 3.5,
        '秋天': 3.0,
        '春天': 3.0,
    }
    
    ITEM_KEYWORDS = {
        # 重要道具
        'thermal stone': 3.0,
        'ice box': 3.0,
        'crock pot': 3.5,
        'science machine': 3.0,
        'alchemy engine': 3.0,
        '保温石': 3.0,
        '冰箱': 3.0,
        '烹饪锅': 3.5,
        '科学机器': 3.0,
        '炼金引擎': 3.0,
        
        # 食物
        'pierogi': 3.0,
        'meatball': 2.5,
        'honey ham': 2.5,
        '饺子': 3.0,
        '肉丸': 2.5,
        '蜜汁火腿': 2.5,
    }
    
    SPECIAL_KEYWORDS = {
        # 角色名
        'wilson': 2.5,
        'willow': 2.5,
        'wolfgang': 2.5,
        'wendy': 2.5,
        'wickerbottom': 2.5,
        'woodie': 2.5,
        'maxwell': 2.5,
        'wigfrid': 2.5,
        'webber': 2.5,
        'warly': 2.5,
        'wormwood': 2.5,
        'wortox': 2.5,
        'wurt': 2.5,
        'walter': 2.5,
        'wanda': 2.5,
    }


class EldenRingConfig(GameKeywordConfig):
    """Elden Ring 特定配置"""
    
    ENEMY_KEYWORDS = {
        # 主要Boss
        'margit': 4.0,
        'godrick': 4.0,
        'radahn': 4.5,
        'malenia': 5.0,
        'radagon': 4.5,
        'elden beast': 5.0,
        '葛瑞克': 4.0,
        '拉塔恩': 4.5,
        '玛莲妮亚': 5.0,
        '拉达冈': 4.5,
        '艾尔登之兽': 5.0,
        
        # 常见敌人
        'crucible knight': 3.5,
        'tree sentinel': 3.5,
        'godskin': 3.5,
        '熔炉骑士': 3.5,
        '大树守卫': 3.5,
        '神皮': 3.5,
    }
    
    TACTICAL_KEYWORDS = {
        # 构建相关
        'strength build': 4.0,
        'dexterity build': 4.0,
        'intelligence build': 4.0,
        'faith build': 4.0,
        'hybrid build': 3.5,
        '力量流': 4.0,
        '敏捷流': 4.0,
        '智力流': 4.0,
        '信仰流': 4.0,
        '混合流': 3.5,
        
        # 战斗相关
        'dodge': 3.0,
        'parry': 3.0,
        'stance break': 3.5,
        'critical hit': 3.5,
        '闪避': 3.0,
        '格挡': 3.0,
        '破防': 3.5,
        '暴击': 3.5,
    }
    
    ITEM_KEYWORDS = {
        # 武器类型
        'katana': 3.0,
        'greatsword': 3.0,
        'colossal sword': 3.0,
        'staff': 3.0,
        'seal': 3.0,
        '武士刀': 3.0,
        '大剑': 3.0,
        '特大剑': 3.0,
        '法杖': 3.0,
        '圣印记': 3.0,
        
        # 战灰
        'ash of war': 3.5,
        'bloodhound step': 3.5,
        'lion claw': 3.0,
        'moonveil': 3.5,
        '战灰': 3.5,
        '猎犬步伐': 3.5,
        '狮子爪': 3.0,
        '月隐': 3.5,
    }


class Civilization6Config(GameKeywordConfig):
    """Civilization 6 特定配置"""
    
    SPECIAL_KEYWORDS = {
        # 文明
        'america': 3.0,
        'china': 3.0,
        'egypt': 3.0,
        'germany': 3.0,
        'greece': 3.0,
        'rome': 3.0,
        'russia': 3.0,
        '美国': 3.0,
        '中国': 3.0,
        '埃及': 3.0,
        '德国': 3.0,
        '希腊': 3.0,
        '罗马': 3.0,
        '俄罗斯': 3.0,
    }
    
    TACTICAL_KEYWORDS = {
        # 胜利条件
        'science victory': 4.0,
        'culture victory': 4.0,
        'domination victory': 4.0,
        'religious victory': 4.0,
        'diplomatic victory': 4.0,
        '科技胜利': 4.0,
        '文化胜利': 4.0,
        '征服胜利': 4.0,
        '宗教胜利': 4.0,
        '外交胜利': 4.0,
        
        # 游戏概念
        'district': 3.5,
        'wonder': 3.5,
        'policy': 3.0,
        'government': 3.0,
        '区域': 3.5,
        '奇观': 3.5,
        '政策': 3.0,
        '政体': 3.0,
    }
    
    ITEM_KEYWORDS = {
        # 重要单位
        'settler': 3.0,
        'builder': 3.0,
        'trader': 3.0,
        'spy': 3.0,
        '开拓者': 3.0,
        '建造者': 3.0,
        '商人': 3.0,
        '间谍': 3.0,
        
        # 资源
        'strategic resource': 3.0,
        'luxury resource': 3.0,
        'campus': 3.5,
        'theater square': 3.5,
        '战略资源': 3.0,
        '奢侈资源': 3.0,
        '学院': 3.5,
        '剧院广场': 3.5,
    } 